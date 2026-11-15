"""Schema snapshot: fails CI when a tool signature changes unintentionally.
Update intentionally with: UPDATE_SNAPSHOTS=1 pytest tests/contract"""
import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

SNAP = Path(__file__).parent / "snapshots"


async def _schema(server) -> dict:
    async with create_connected_server_and_client_session(server._mcp_server) as s:
        tools = (await s.list_tools()).tools
        return {t.name: {"input": t.inputSchema, "output": t.outputSchema,
                         "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else None}
                for t in sorted(tools, key=lambda t: t.name)}


@pytest.mark.parametrize("name", ["portfolio", "marketplace", "workspace"])
async def test_tool_schema_snapshot(name):
    mod = __import__(f"mcp_servers.{name}.server", fromlist=["mcp"])
    current = await _schema(mod.mcp)
    path = SNAP / f"{name}.json"
    if os.environ.get("UPDATE_SNAPSHOTS") == "1" or not path.exists():
        SNAP.mkdir(exist_ok=True)
        path.write_text(json.dumps(current, indent=1, sort_keys=True), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(json.dumps(current, sort_keys=True)), \
        f"{name} tool schema changed; if intended run UPDATE_SNAPSHOTS=1 pytest tests/contract"


async def test_write_tools_have_annotations():
    from mcp_servers.marketplace.server import mcp

    s = await _schema(mcp)
    for t in ("create_proposal_draft", "submit_proposal", "send_message"):
        assert s[t]["annotations"]["readOnlyHint"] is False
        assert "idempotency_key" in json.dumps(s[t]["input"])
    assert s["submit_proposal"]["annotations"]["destructiveHint"] is True
    for t in ("search_jobs", "get_job", "get_client_history"):
        assert s[t]["annotations"]["readOnlyHint"] is True
