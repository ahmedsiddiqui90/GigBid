"""The single marketplace port (R1). Two adapters implement it: GigSim and live Upwork (official MCP).

The adapter is chosen by config (`marketplace.adapter`), so graphs and MCP tools never know which
marketplace they are talking to.
"""
from __future__ import annotations

from typing import Any, Protocol


class MarketplaceUnavailable(Exception):
    """Raised after bounded retries fail (5xx, timeouts, connection refused)."""


class MarketplaceRateLimited(MarketplaceUnavailable):
    pass


class MarketplaceError(Exception):
    """A 4xx the caller must handle (not found, not enough Connects, validation)."""

    def __init__(self, status: int, detail: Any):
        super().__init__(f"{status}: {detail}")
        self.status, self.detail = status, detail


class MarketplacePort(Protocol):
    name: str

    async def search_jobs(self, query: str, category: str | None = None, limit: int = 20) -> list[dict]: ...
    async def get_job(self, job_id: str) -> dict: ...
    async def get_client_history(self, client_id: str) -> dict: ...
    async def get_market_stats(self, category: str) -> dict: ...
    async def get_connects_balance(self, freelancer_id: str) -> dict: ...
    async def list_messages(self, freelancer_id: str) -> list[dict]: ...
    async def list_events(self, freelancer_id: str, since: int = 0) -> list[dict]: ...
    async def create_proposal_draft(self, payload: dict, idempotency_key: str) -> dict: ...
    async def submit_proposal(self, freelancer_id: str, proposal_id: str, idempotency_key: str) -> dict: ...
    async def send_message(self, freelancer_id: str, thread_id: str, text: str, idempotency_key: str) -> dict: ...


def get_adapter(user_token: str | None = None) -> MarketplacePort:
    from agent.settings import config

    kind = config().marketplace["adapter"]
    if kind == "gigsim":
        from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter

        return GigSimAdapter()
    if kind == "upwork_live":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter

        return UpworkLiveAdapter(access_token=user_token)
    raise ValueError(f"unknown marketplace adapter {kind!r}")
