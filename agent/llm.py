"""Model access routed by node, from agent/config.yaml.

Every call returns the parsed value plus a Usage record (tokens, cost, latency) so the graph can
enforce token budgets and report cost per node. The `offline` profile runs a caller-supplied
deterministic heuristic instead of an LLM (used in tests/CI and when no API key is configured).
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

from agent.prompts import load_prompt
from agent.settings import config

T = TypeVar("T", bound=BaseModel)


@dataclass
class Usage:
    node: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    fallback: bool = False

    def dict(self) -> dict:
        return asdict(self)


def model_for(node: str) -> str:
    cfg = config()
    prof = cfg.profiles[cfg.profile]
    if prof.get("provider") == "heuristic":
        return "heuristic"
    return prof["nodes"].get(node, prof["nodes"]["default"])


def _cost(model: str, tin: int, tout: int) -> float:
    pin, pout = config().model_prices.get(model, [0.0, 0.0])
    return (tin * pin + tout * pout) / 1_000_000


_clients: dict[str, object] = {}


def _chat(model: str):
    from langchain_openai import ChatOpenAI

    cfg = config()
    prof = cfg.profiles[cfg.profile]
    if model not in _clients:
        _clients[model] = ChatOpenAI(
            model=model,
            base_url=prof["base_url"],
            api_key=os.environ.get(prof["api_key_env"], ""),
            temperature=cfg.llm["temperature"],
            timeout=cfg.llm["timeout_s"],
            max_retries=cfg.llm["max_retries"],
        )
    return _clients[model]


def is_offline() -> bool:
    return model_for("default") == "heuristic"


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", str(text), flags=re.S).strip()


def _extract_json(text: str) -> dict:
    text = _strip_think(text)
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


async def _invoke(node: str, model: str, system: str, user: str, json_mode: bool):
    llm = _chat(model)
    if json_mode:
        llm = llm.bind(response_format={"type": "json_object"})
    t0 = time.perf_counter()
    msg = await llm.ainvoke([("system", system), ("user", user)])
    dt = time.perf_counter() - t0
    um = getattr(msg, "usage_metadata", None) or {}
    tin, tout = um.get("input_tokens", 0), um.get("output_tokens", 0)
    return msg.content, Usage(node, model, tin, tout, _cost(model, tin, tout), dt)


async def llm_json(
    node: str,
    prompt: str,
    schema: type[T],
    heuristic: Callable[[], T],
    system_prompt: str = "system",
    **variables: object,
) -> tuple[T, Usage]:
    """Render prompt, call the node's model in JSON mode, validate into `schema`.

    On repeated failure, retries on the fallback model, then on the heuristic.
    """
    model = model_for(node)
    if model == "heuristic":
        t0 = time.perf_counter()
        val = heuristic()
        return val, Usage(node, "heuristic", latency_s=time.perf_counter() - t0)
    system = load_prompt(system_prompt).render()
    user = load_prompt(prompt).render(schema=json.dumps(schema.model_json_schema()), **variables)
    prof = config().profiles[config().profile]
    last_err: Exception | None = None
    for m, is_fb in ((model, False), (prof.get("fallback", model), True)):
        try:
            text, usage = await _invoke(node, m, system, user, json_mode=True)
            usage.fallback = is_fb
            return schema.model_validate(_extract_json(text)), usage
        except (ValidationError, json.JSONDecodeError, Exception) as e:  # noqa: BLE001
            last_err = e
    val = heuristic()
    u = Usage(node, "heuristic", fallback=True)
    u.model = f"heuristic (after error: {type(last_err).__name__})"
    return val, u


async def llm_text(
    node: str, prompt: str, heuristic: Callable[[], str], system_prompt: str = "system", **variables: object
) -> tuple[str, Usage]:
    model = model_for(node)
    if model == "heuristic":
        return heuristic(), Usage(node, "heuristic")
    system = load_prompt(system_prompt).render()
    user = load_prompt(prompt).render(**variables)
    prof = config().profiles[config().profile]
    for m, is_fb in ((model, False), (prof.get("fallback", model), True)):
        try:
            text, usage = await _invoke(node, m, system, user, json_mode=False)
            usage.fallback = is_fb
            return _strip_think(text), usage
        except Exception:  # noqa: BLE001
            continue
    return heuristic(), Usage(node, "heuristic", fallback=True)
