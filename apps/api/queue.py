"""Enqueue background work on the Arq worker (graph runs never execute inside web requests)."""
from __future__ import annotations

from arq import create_pool
from arq.connections import RedisSettings

from agent.settings import env

_pool = None


async def pool():
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(env().redis_url))
    return _pool


async def enqueue(fn: str, *args, job_id: str | None = None, **kw):
    """job_id makes enqueueing idempotent: Arq ignores a second job with the same id while it exists."""
    p = await pool()
    return await p.enqueue_job(fn, *args, _job_id=job_id, **kw)
