"""Long-term memory on a LangGraph store (PostgresStore). Namespaces:
  ("style_candidates", user)  pattern -> {count, examples}         (not used by agents)
  ("style", user)             pattern -> {rule, count, promoted_at} (read by the Proposal Writer)
  ("outcome", user)           category -> {submitted, replied, hired} (read by Decide/Pricing)
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from langgraph.store.base import BaseStore

from agent.memory.promotion_rules import edit_patterns, rule_text
from agent.settings import config, env


@asynccontextmanager
async def open_store():
    from langgraph.store.postgres.aio import AsyncPostgresStore

    async with AsyncPostgresStore.from_conn_string(env().database_url) as store:
        await store.setup()
        yield store


async def record_edit(store: BaseStore, user: str, before: str, after: str) -> list[str]:
    """Diff an edit into patterns; promote patterns that reached the threshold. Returns newly promoted."""
    promoted = []
    need = int(config().memory["style_promotion_min_occurrences"])
    for p in edit_patterns(before, after):
        cand = await store.aget(("style_candidates", user), p)
        count = (cand.value["count"] if cand else 0) + 1
        await store.aput(("style_candidates", user), p, {"count": count, "last_seen": time.time()})
        if count >= need and not await store.aget(("style", user), p):
            await store.aput(("style", user), p, {"rule": rule_text(p), "count": count, "promoted_at": time.time(),
                                                  "promotion_rule": f"pattern seen in >= {need} separate edits"})
            promoted.append(p)
    return promoted


async def style_rules(store: BaseStore | None, user: str) -> list[str]:
    if store is None:
        return []
    return [i.value["rule"] for i in await store.asearch(("style", user), limit=50)]


async def record_outcome(store: BaseStore, user: str, category: str, event: str) -> None:
    item = await store.aget(("outcome", user), category)
    v = item.value if item else {"submitted": 0, "replied": 0, "hired": 0}
    key = {"submitted": "submitted", "replied": "replied", "interview": None, "hired": "hired"}.get(event)
    if key:
        v[key] += 1
        await store.aput(("outcome", user), category, v)


async def outcome_rate(store: BaseStore | None, user: str, category: str) -> float | None:
    if store is None:
        return None
    item = await store.aget(("outcome", user), category)
    if not item or item.value["submitted"] < int(config().memory["outcome_min_samples"]):
        return None
    return item.value["replied"] / item.value["submitted"]


async def list_memory(store: BaseStore, user: str) -> dict:
    out = {}
    for ns in ("style", "style_candidates", "outcome"):
        out[ns] = [{"key": i.key, **i.value} for i in await store.asearch((ns, user), limit=100)]
    return out


async def delete_memory(store: BaseStore, user: str, ns: str, key: str) -> None:
    await store.adelete((ns, user), key)
    if ns == "style":
        await store.adelete(("style_candidates", user), key)
