"""Shared node wrapper: budgets (C4), streaming progress, execution trace, MCP calls."""
from __future__ import annotations

import functools
import time
from typing import Any, Awaitable, Callable

from agent.llm import Usage
from agent.mcp_client import call
from agent.settings import config

TERMINAL = {"needs_attention", "blocked", "dead_letter", "skipped", "rejected", "submitted", "sent",
            "waiting_marketplace", "watch"}


def _writer():
    try:
        from langgraph.config import get_stream_writer

        return get_stream_writer()
    except Exception:  # noqa: BLE001 - outside a graph run
        return lambda _x: None


def node(name: str) -> Callable:
    """Wrap a node: no-op once the run is terminal, enforce step/token budgets, record trace + progress."""

    def deco(fn: Callable[[dict], Awaitable[dict]]):
        @functools.wraps(fn)
        async def wrapper(state: dict) -> dict:
            if state.get("status") in TERMINAL:
                return {}
            b = config().budgets
            tokens = sum(u.get("tokens_in", 0) + u.get("tokens_out", 0) for u in state.get("usage", []))
            if state.get("steps", 0) >= b["max_graph_steps"] or tokens >= b["max_tokens_per_thread"]:
                return {"status": "needs_attention",
                        "errors": [f"budget exceeded at {name}: steps={state.get('steps', 0)} tokens={tokens}"]}
            w = _writer()
            w({"node": name, "phase": "start", "ts": time.time()})
            t0 = time.perf_counter()
            out = await fn(state) or {}
            dt = round(time.perf_counter() - t0, 3)
            out["steps"] = 1
            out.setdefault("trace", [])
            out["trace"] = [{"node": name, "latency_s": dt, **t} for t in out["trace"]] or [{"node": name, "latency_s": dt}]
            w({"node": name, "phase": "end", "latency_s": dt, "status": out.get("status"),
               "summary": _summary(name, out)})
            return out

        return wrapper

    return deco


def _summary(name: str, out: dict) -> str:
    for k in ("decision", "risk", "fit", "price", "critique", "compliance", "submission", "verification"):
        if k in out and isinstance(out[k], dict):
            v = out[k]
            return str({kk: v[kk] for kk in list(v)[:3]})[:200]
    return ""


def usage(u: Usage) -> list[dict]:
    return [u.dict()]


async def tool(state: dict, node_name: str, tool_name: str, args: dict) -> tuple[Any, dict]:
    """Call an MCP tool for a node; returns (result, trace entry)."""
    t0 = time.perf_counter()
    res = await call(node_name, state.get("user_id", "local"), state.get("trace_id", "-"), tool_name, args)
    short = str(res)[:300]
    return res, {"tool": tool_name, "args": {k: (str(v)[:120]) for k, v in args.items()}, "result": short,
                 "tool_latency_s": round(time.perf_counter() - t0, 3)}
