"""GigSim adapter: HTTP client with bounded retries, exponential backoff + jitter, Retry-After."""
from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from agent.marketplace_port import MarketplaceError, MarketplaceRateLimited, MarketplaceUnavailable
from agent.settings import config, env


class GigSimAdapter:
    name = "gigsim"

    def __init__(self, base_url: str | None = None, token: str | None = None, transport: Any = None):
        self.base = base_url or env().gigsim_base_url
        self.headers = {"Authorization": f"Bearer {token or env().gigsim_api_token}"}
        self.timeout = config().marketplace["request_timeout_s"]
        self.retries = config().marketplace["max_retries"]
        self.transport = transport

    async def _req(self, method: str, path: str, idem: str | None = None, **kw: Any) -> Any:
        headers = dict(self.headers)
        if idem:
            headers["Idempotency-Key"] = idem
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(base_url=self.base, timeout=self.timeout, transport=self.transport) as c:
                    r = await c.request(method, path, headers=headers, **kw)
                if r.status_code == 429:
                    last = MarketplaceRateLimited("rate limited")
                    await asyncio.sleep(float(r.headers.get("Retry-After", "2")) + random.random())
                    continue
                if r.status_code >= 500:
                    last = MarketplaceUnavailable(f"gigsim {r.status_code}")
                elif r.status_code >= 400:
                    raise MarketplaceError(r.status_code, r.json().get("detail", r.text))
                else:
                    return r.json()
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
                last = MarketplaceUnavailable(f"gigsim unreachable: {type(e).__name__}")
            await asyncio.sleep(min(8.0, 0.5 * 2**attempt) + random.random() * 0.3)
        raise last or MarketplaceUnavailable("gigsim failed")

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(base_url=self.base, timeout=3) as c:
                return (await c.get("/health")).status_code == 200
        except httpx.HTTPError:
            return False

    async def search_jobs(self, query: str, category: str | None = None, limit: int = 20) -> list[dict]:
        params = {"q": query, "limit": limit, **({"category": category} if category else {})}
        return (await self._req("GET", "/jobs", params=params))["jobs"]

    async def get_job(self, job_id: str) -> dict:
        return await self._req("GET", f"/jobs/{job_id}")

    async def get_client_history(self, client_id: str) -> dict:
        return await self._req("GET", f"/clients/{client_id}")

    async def get_market_stats(self, category: str) -> dict:
        return await self._req("GET", "/market/stats", params={"category": category})

    async def get_connects_balance(self, freelancer_id: str) -> dict:
        return await self._req("GET", f"/freelancers/{freelancer_id}/connects")

    async def list_messages(self, freelancer_id: str) -> list[dict]:
        return (await self._req("GET", "/messages", params={"freelancer_id": freelancer_id}))["threads"]

    async def list_events(self, freelancer_id: str, since: int = 0) -> list[dict]:
        return (await self._req("GET", "/events", params={"freelancer_id": freelancer_id, "since": since}))["events"]

    async def create_proposal_draft(self, payload: dict, idempotency_key: str) -> dict:
        return await self._req("POST", "/proposals", idem=idempotency_key, json={**payload, "submit": False})

    async def submit_proposal(self, freelancer_id: str, proposal_id: str, idempotency_key: str) -> dict:
        return await self._req("POST", f"/proposals/{proposal_id}/submit", idem=idempotency_key)

    async def send_message(self, freelancer_id: str, thread_id: str, text: str, idempotency_key: str) -> dict:
        return await self._req("POST", "/messages", idem=idempotency_key,
                               json={"freelancer_id": freelancer_id, "thread_id": thread_id, "text": text})
