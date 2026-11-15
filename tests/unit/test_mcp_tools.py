"""MCP tool tests through an in-memory MCP client session (no HTTP)."""
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from agent import db


def _data(res):
    if res.structuredContent:
        sc = res.structuredContent
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(res.content[0].text)


@pytest.fixture(autouse=True)
async def schema():
    await db.init_schema()


async def test_marketplace_read_and_dry_run(gigsim_adapter):
    from mcp_servers.marketplace.server import mcp

    async with create_connected_server_and_client_session(mcp._mcp_server) as s:
        jobs = _data(await s.call_tool("search_jobs", {"query": "churn"}))["jobs"]
        assert jobs, "expected jobs"
        jid = jobs[0]["job_id"]
        prev = _data(await s.call_tool("create_proposal_draft", {"input": {
            "freelancer_id": "t1", "job_id": jid, "cover_letter": "x" * 60, "bid_amount": 300,
            "idempotency_key": "test-dry-run-1", "dry_run": True}}))
        assert prev["status"] == "dry_run" and prev["connects_cost"] > 0
        assert prev["would_send"]["bid_amount"] == 300


async def test_marketplace_write_validation(gigsim_adapter):
    from mcp_servers.marketplace.server import mcp

    async with create_connected_server_and_client_session(mcp._mcp_server) as s:
        res = await s.call_tool("create_proposal_draft", {"input": {
            "freelancer_id": "t1", "job_id": "dev-ai_ml-001", "cover_letter": "too short", "bid_amount": -5,
            "idempotency_key": "k"}})
        assert res.isError


async def test_submit_is_idempotent(gigsim_adapter):
    import uuid

    from mcp_servers.marketplace.server import mcp

    key = uuid.uuid4().hex
    async with create_connected_server_and_client_session(mcp._mcp_server) as s:
        d = _data(await s.call_tool("create_proposal_draft", {"input": {
            "freelancer_id": f"t-{key}", "job_id": "dev-ai_ml-001", "cover_letter": "y" * 80, "bid_amount": 400,
            "idempotency_key": f"draft-{key}"}}))
        args = {"input": {"freelancer_id": f"t-{key}", "proposal_id": d["id"], "job_id": "dev-ai_ml-001",
                          "idempotency_key": f"submit-{key}"}}
        first = _data(await s.call_tool("submit_proposal", args))
        second = _data(await s.call_tool("submit_proposal", args))
        assert first["status"] == "submitted" and second["status"] == "replayed"
        bal = _data(await s.call_tool("get_connects_balance", {"freelancer_id": f"t-{key}"}))
        assert bal["balance"] == 120 - first["connects_cost"]


async def test_portfolio_tools_resources_prompts():
    from mcp_servers.portfolio.server import mcp

    async with create_connected_server_and_client_session(mcp._mcp_server) as s:
        ev = _data(await s.call_tool("search_evidence", {"requirement": "churn prediction with XGBoost", "k": 3,
                                                          "filters": {"persona": "ai_ml"}}))
        assert ev["items"] and ev["items"][0]["id"]
        skills = _data(await s.call_tool("list_skills", {"persona": "ai_ml"}))
        assert "Python" in skills["skills"]
        templates = await s.list_resource_templates()
        assert {t.uriTemplate for t in templates.resourceTemplates} >= {"portfolio://case/{id}", "portfolio://proposal/{id}"}
        prompts = await s.list_prompts()
        assert any(p.name == "answer_screening_question" for p in prompts.prompts)


async def test_workspace_slots():
    from mcp_servers.workspace.server import mcp

    async with create_connected_server_and_client_session(mcp._mcp_server) as s:
        slots = _data(await s.call_tool("free_slots", {"days_ahead": 7}))
        assert len(slots["slots"]) >= 1
