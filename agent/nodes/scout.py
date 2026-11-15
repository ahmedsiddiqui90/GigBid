"""Scout: run saved searches, de-duplicate, queue new jobs. MCP: marketplace read.

De-duplication: by job id, and by a normalised hash of title + description (catches re-posts).
Called by the worker on each saved search's schedule (not part of a per-job thread).
"""
from __future__ import annotations

import hashlib
import re

from agent.mcp_client import call


def dedupe_hash(job: dict) -> str:
    norm = re.sub(r"\W+", " ", f"{job.get('title', '')} {job.get('description', '')}".lower()).strip()
    return hashlib.sha256(norm.encode()).hexdigest()[:20]


async def scout(user_id: int, trace_id: str, query: str, category: str | None, seen_ids: set[str],
                seen_hashes: set[str], limit: int = 20) -> list[dict]:
    res = await call("scout", user_id, trace_id, "search_jobs", {"query": query, "category": category, "limit": limit})
    new = []
    for j in res.get("jobs", []):
        h = dedupe_hash(j)
        if j["job_id"] in seen_ids or h in seen_hashes:
            continue
        seen_ids.add(j["job_id"])
        seen_hashes.add(h)
        new.append({**j, "dedupe_hash": h})
    return new
