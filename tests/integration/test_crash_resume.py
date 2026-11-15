"""Durability (C6): a proposal waiting for approval survives a restart and is submitted exactly once.

Needs GigSim (:8081) and the MCP servers (:8101-8103) running; skipped otherwise.
Scenario: run the bid graph to the approval interrupt -> throw away the graph and its DB connection
("kill the API/worker") -> build a fresh graph on the same Postgres checkpointer -> approve -> submitted.
Then replay the submit step again (as if the worker crashed after submitting but before checkpointing):
the marketplace reports an idempotent replay and Connects are spent once.
"""
import uuid

import httpx
import pytest

from agent import db
from agent.settings import env


def _up() -> bool:
    try:
        return httpx.get("http://localhost:8081/health", timeout=2).status_code == 200 and \
            httpx.get("http://localhost:8102/mcp", timeout=2).status_code in (401, 405, 406)
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _up(), reason="GigSim / MCP servers not running")


async def test_crash_and_resume_submits_exactly_once():
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.types import Command

    from agent.graphs.bid_graph import build_bid_graph
    from agent.nodes.approval import submit

    await db.init_schema()
    fid = f"fl-crash-{uuid.uuid4().hex[:6]}"
    thread = {"configurable": {"thread_id": f"test-crash:{fid}"}}
    state = {"user_id": "crash-test", "persona": "ai_ml", "freelancer_id": fid, "floor_rate": 35, "hourly_rate": 45,
             "job_id": "dev-ai_ml-001", "run_id": "t", "trace_id": "t"}

    async with AsyncPostgresSaver.from_conn_string(env().database_url) as cp:
        await cp.setup()
        g = build_bid_graph(cp)
        await g.ainvoke(state, thread)
        snap = await g.aget_state(thread)
        assert snap.next == ("approval",), f"expected to wait for approval, got {snap.next} {snap.values.get('status')}"
    # --- process "crashed": graph and connection are gone ---

    async with AsyncPostgresSaver.from_conn_string(env().database_url) as cp2:
        g2 = build_bid_graph(cp2)
        out = await g2.ainvoke(Command(resume={"action": "approve"}), thread)
        assert out["status"] == "submitted"
        spent = out["submission"]["connects_cost"]

        # Crash after submit but before the checkpoint: the submit step runs again with the same state.
        again = await submit(dict((await g2.aget_state(thread)).values, status=None))
        assert again["submission"]["status"] == "replayed"

    async with httpx.AsyncClient() as c:
        bal = (await c.get(f"http://localhost:8081/freelancers/{fid}/connects",
                           headers={"Authorization": f"Bearer {env().gigsim_api_token}"})).json()["balance"]
    assert bal == 120 - spent, "Connects must be spent exactly once"
