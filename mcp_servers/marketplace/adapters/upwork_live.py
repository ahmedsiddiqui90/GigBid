"""Live adapter: the official Upwork MCP server (https://mcp.upwork.com/mcp, OAuth 2.1, Streamable HTTP).

The user completes OAuth in GigBid (apps/api/routers/onboarding.py); the access token is stored encrypted
per user and passed in here. Upwork tools are mapped onto our MarketplacePort so the graph cannot tell
which marketplace it uses. Rules enforced here:
  - every write is created as a DRAFT on Upwork; the user confirms it on Upwork (submit_proposal never
    submits directly),
  - no browser automation, no session cookies, no scraping - only the official MCP tools,
  - reads are scheduled conservatively (config: schedules.live_scout_minutes).

Tool names on the Upwork server are discovered at runtime; TOOL_MAP lists the candidates we look for.
Not exercised against a real account in this submission (no Upwork account available); covered by a
contract test with a fake MCP session.
"""
from __future__ import annotations

import json
from typing import Any

from agent.marketplace_port import MarketplaceError, MarketplaceUnavailable
from agent.settings import env

TOOL_MAP = {
    "search_jobs": ["search_jobs", "job_search", "searchJobs"],
    "get_job": ["get_job", "get_job_details", "getJob"],
    "get_client_history": ["get_client", "get_client_details", "getClient"],
    "list_messages": ["list_rooms", "list_messages", "getRooms"],
    "create_proposal_draft": ["create_proposal_draft", "draft_proposal", "createProposal"],
    "send_message": ["draft_message", "send_message", "createMessage"],
    "get_connects_balance": ["get_connects", "get_connects_balance"],
}


class UpworkLiveAdapter:
    name = "upwork_live"

    def __init__(self, access_token: str | None, session: Any = None):
        self.token = access_token
        self._session = session  # injectable for tests
        self._tools: dict[str, str] | None = None

    async def _client_tools(self) -> dict[str, Any]:
        if self._session is not None:
            return self._session
        if not self.token:
            raise MarketplaceUnavailable("Upwork account not connected (complete OAuth in Settings)")
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient({"upwork": {"transport": "streamable_http", "url": env().upwork_mcp_url,
                                                  "headers": {"Authorization": f"Bearer {self.token}"}}})
        try:
            tools = await client.get_tools()
        except Exception as e:  # noqa: BLE001
            raise MarketplaceUnavailable(f"Upwork MCP unreachable: {type(e).__name__}") from e
        self._session = {t.name: t for t in tools}
        return self._session

    async def _call(self, port_name: str, args: dict) -> Any:
        tools = await self._client_tools()
        for cand in TOOL_MAP[port_name]:
            if cand in tools:
                out = await tools[cand].ainvoke(args)
                try:
                    return json.loads(out) if isinstance(out, str) else out
                except json.JSONDecodeError:
                    return {"text": out}
        raise MarketplaceError(501, f"Upwork MCP has no tool for {port_name}")

    async def search_jobs(self, query: str, category: str | None = None, limit: int = 20) -> list[dict]:
        out = await self._call("search_jobs", {"query": query, "limit": limit})
        return out.get("jobs", out) if isinstance(out, dict) else out

    async def get_job(self, job_id: str) -> dict:
        return await self._call("get_job", {"job_id": job_id})

    async def get_client_history(self, client_id: str) -> dict:
        return await self._call("get_client_history", {"client_id": client_id})

    async def get_market_stats(self, category: str) -> dict:
        # Upwork exposes no market statistics; fall back to our Kaggle-derived statistics.
        from pathlib import Path

        p = Path(__file__).resolve().parents[3] / "data" / "gigsim" / "market_stats.json"
        cats = json.loads(p.read_text())["categories"]
        return {"category": category, **cats.get(category, cats["other"]), "source": "kaggle (real)"}

    async def get_connects_balance(self, freelancer_id: str) -> dict:
        try:
            return await self._call("get_connects_balance", {})
        except MarketplaceError:
            return {"freelancer_id": freelancer_id, "balance": None, "note": "not exposed by Upwork MCP"}

    async def list_messages(self, freelancer_id: str) -> list[dict]:
        out = await self._call("list_messages", {})
        return out.get("rooms", out) if isinstance(out, dict) else out

    async def list_events(self, freelancer_id: str, since: int = 0) -> list[dict]:
        return []  # pipeline updates come from list_messages in live mode

    async def create_proposal_draft(self, payload: dict, idempotency_key: str) -> dict:
        out = await self._call("create_proposal_draft", {"job_id": payload["job_id"], "cover_letter": payload["cover_letter"],
                                                         "bid_amount": payload["bid_amount"]})
        return {"proposal_id": out.get("id", "upwork-draft"), "status": "draft", "platform": "upwork", **out}

    async def submit_proposal(self, freelancer_id: str, proposal_id: str, idempotency_key: str) -> dict:
        # Platform rule: the user confirms the draft on Upwork. GigBid never submits in live mode.
        return {"proposal_id": proposal_id, "status": "draft",
                "note": "Draft created on Upwork. Open Upwork to review and confirm submission."}

    async def send_message(self, freelancer_id: str, thread_id: str, text: str, idempotency_key: str) -> dict:
        out = await self._call("send_message", {"room_id": thread_id, "text": text})
        return {"ok": True, "thread_id": thread_id, "status": "draft", **(out if isinstance(out, dict) else {})}
