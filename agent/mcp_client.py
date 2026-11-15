"""MultiServerMCPClient setup + per-agent tool allowlists (A6).

Each node gets only the tools named in config `mcp.allowlists[node]`. Calls have a timeout, bounded
retries with backoff, and raise MarketplaceDown when the marketplace server is unreachable, which puts
the run into a visible degraded state instead of failing silently.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from agent.settings import config, env

SERVER_OF = {}  # tool name -> server, filled on first discovery


class MarketplaceDown(Exception):
    pass


class ToolNotAllowed(Exception):
    pass


def _connections(user_id: Any, trace_id: str) -> dict:
    h = {"Authorization": f"Bearer {env().mcp_bearer_token}", "X-GigBid-User": str(user_id), "X-Trace-Id": trace_id}
    return {name: {"transport": "streamable_http", "url": url, "headers": h, "timeout": 30}
            for name, url in config().mcp["servers"].items()}


_tool_cache: dict[tuple, dict] = {}


async def tools_for(node: str, user_id: Any, trace_id: str) -> dict[str, Any]:
    """LangChain tools for a node, filtered by its allowlist."""
    allowed = set(config().mcp["allowlists"].get(node, []))
    if not allowed:
        return {}
    key = (str(user_id), trace_id)
    if key not in _tool_cache:
        client = MultiServerMCPClient(_connections(user_id, trace_id))
        tools: dict[str, Any] = {}
        for server in config().mcp["servers"]:
            try:
                for t in await client.get_tools(server_name=server):
                    tools[t.name] = t
                    SERVER_OF[t.name] = server
            except Exception:  # noqa: BLE001 - a down server is handled at call time
                continue
        if len(_tool_cache) > 200:
            _tool_cache.clear()
        _tool_cache[key] = tools
    return {n: t for n, t in _tool_cache[key].items() if n in allowed}


def _parse(out: Any) -> Any:
    if isinstance(out, tuple):
        out = out[0]
    if isinstance(out, list):
        texts = [b.get("text", "") if isinstance(b, dict) else getattr(b, "text", str(b)) for b in out]
        out = "".join(texts)
    if isinstance(out, str):
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return {"text": out}
    return out


async def call(node: str, user_id: Any, trace_id: str, tool: str, args: dict, retries: int = 2,
               timeout: float = 45) -> Any:
    tools = await tools_for(node, user_id, trace_id)
    if tool not in tools:
        if tool in config().mcp["allowlists"].get(node, []):
            # allowed but not discovered -> its server is down
            _tool_cache.pop((str(user_id), trace_id), None)
            raise MarketplaceDown(f"MCP server for '{tool}' is unavailable")
        raise ToolNotAllowed(f"node {node!r} may not call {tool!r}")
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            res = _parse(await asyncio.wait_for(tools[tool].ainvoke(args), timeout))
            if isinstance(res, dict) and "unavailable" in str(res.get("text", "")).lower():
                raise MarketplaceDown(res["text"])
            return res
        except MarketplaceDown:
            raise
        except Exception as e:  # noqa: BLE001
            last = e
            msg = str(e).lower()
            if any(s in msg for s in ("unreachable", "unavailable", "connect", "503")):
                last = MarketplaceDown(f"{tool}: {e}")
            await asyncio.sleep(0.5 * 2**attempt)
    if isinstance(last, MarketplaceDown) or SERVER_OF.get(tool) == "marketplace":
        raise MarketplaceDown(f"{tool} failed after retries: {last}")
    raise last  # type: ignore[misc]
