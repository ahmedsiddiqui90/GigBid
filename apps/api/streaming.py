"""SSE bridge: LangGraph stream events (published by the worker to Redis) -> browser."""
from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis
from sse_starlette.sse import EventSourceResponse

from agent import db
from agent.settings import env


def run_stream(run_id: str) -> EventSourceResponse:
    async def gen():
        # Replay what already happened, then follow live events.
        for s in await db.fetch("SELECT node, ts FROM run_steps WHERE run_id=%s ORDER BY id", run_id):
            yield {"event": "node", "data": json.dumps({"node": s["node"], "phase": "end", "replayed": True})}
        r = aioredis.from_url(env().redis_url)
        ps = r.pubsub()
        await ps.subscribe(f"run:{run_id}")
        try:
            idle = 0
            while idle < 600:
                msg = await ps.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg is None:
                    idle += 1
                    yield {"event": "ping", "data": "{}"}
                    await asyncio.sleep(0)
                    continue
                idle = 0
                data = json.loads(msg["data"])
                yield {"event": data.get("type", "node"), "data": json.dumps(data)}
                if data.get("type") == "run" and data.get("status") not in ("running",):
                    break
        finally:
            await ps.unsubscribe()
            await r.aclose()

    return EventSourceResponse(gen())
