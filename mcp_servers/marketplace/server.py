"""Marketplace MCP server: wraps the marketplace port (GigSim or live Upwork) as MCP tools.

Read tools are annotated readOnly/idempotent. Write tools take Pydantic inputs with real constraints,
declare an output schema, require an idempotency key and support dry_run (returns exactly what would be
sent and what it costs). Every call is audited with the caller's user id and trace id.

Run: python -m mcp_servers.marketplace.server   (streamable HTTP on :8102/mcp, bearer auth)
"""
from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent.marketplace_port import MarketplaceError, get_adapter
from agent.settings import config, policy
from mcp_servers.common.guard import RateLimiter, audit, caller, idem_get, idem_put

SERVER = "marketplace"
mcp = FastMCP("gigbid-marketplace", instructions="Freelance marketplace tools (GigSim or Upwork). Writes need human approval upstream.",
              stateless_http=True, json_response=True)
limiter = RateLimiter(config().marketplace["rate_limit_per_minute"])
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


def _connects_cost(job: dict) -> int:
    if "connects_cost" in job:
        return int(job["connects_cost"])
    c = policy()["connects"]
    bmax = (job.get("budget") or {}).get("max") or 0
    return int(c["base"] + sum(t["extra"] for t in c["tiers"] if bmax > t["budget_over"]))


async def _read(ctx: Context | None, tool: str, args: dict, fn) -> Any:
    user, trace = caller(ctx)
    limiter.check(user)
    out = await fn()
    await audit(SERVER, tool, user, trace, args, {"ok": True, "n": len(out) if isinstance(out, list) else 1})
    return out


# ------------------------------------------------------------------ read tools
@mcp.tool(annotations=READ)
async def search_jobs(query: str = "", category: str | None = None, limit: int = 20, ctx: Context = None) -> dict:
    """Search open jobs by keywords (matches title, description, skills). Returns newest first.
    category: ai_ml | web_dev | data_analysis | other."""
    jobs = await _read(ctx, "search_jobs", {"query": query, "category": category},
                       lambda: get_adapter().search_jobs(query, category, min(limit, 50)))
    return {"jobs": jobs}


@mcp.tool(annotations=READ)
async def get_job(job_id: str, ctx: Context = None) -> dict:
    """Full job post (title, description, skills, budget, screening questions, client_id, connects_cost)."""
    return await _read(ctx, "get_job", {"job_id": job_id}, lambda: get_adapter().get_job(job_id))


@mcp.tool(annotations=READ)
async def get_client_history(client_id: str, ctx: Context = None) -> dict:
    """Client's marketplace history: payment verification, hires, total spend, rating, reviews."""
    return await _read(ctx, "get_client_history", {"client_id": client_id},
                       lambda: get_adapter().get_client_history(client_id))


@mcp.tool(annotations=READ)
async def get_market_stats(category: str, ctx: Context = None) -> dict:
    """Pricing statistics for a job category from real historical postings (hourly and fixed budget quartiles)."""
    return await _read(ctx, "get_market_stats", {"category": category}, lambda: get_adapter().get_market_stats(category))


@mcp.tool(annotations=READ)
async def get_connects_balance(freelancer_id: str, ctx: Context = None) -> dict:
    """Current Connects balance for the freelancer."""
    return await _read(ctx, "get_connects_balance", {"freelancer_id": freelancer_id},
                       lambda: get_adapter().get_connects_balance(freelancer_id))


@mcp.tool(annotations=READ)
async def list_messages(freelancer_id: str, ctx: Context = None) -> dict:
    """Client conversation threads for the freelancer, with all messages."""
    threads = await _read(ctx, "list_messages", {"freelancer_id": freelancer_id},
                          lambda: get_adapter().list_messages(freelancer_id))
    return {"threads": threads}


@mcp.tool(annotations=READ)
async def list_events(freelancer_id: str, since: int = 0, ctx: Context = None) -> dict:
    """Pipeline events (viewed, replied, interview, hired, lost) after event id `since`."""
    ev = await _read(ctx, "list_events", {"freelancer_id": freelancer_id, "since": since},
                     lambda: get_adapter().list_events(freelancer_id, since))
    return {"events": ev}


# ------------------------------------------------------------------ write tools
class ProposalDraftInput(BaseModel):
    freelancer_id: str = Field(min_length=1, max_length=100)
    job_id: str = Field(min_length=1, max_length=100)
    cover_letter: str = Field(min_length=50, max_length=5000, description="Approved proposal text")
    bid_amount: float = Field(gt=0, le=100000, description="Bid in USD")
    screening_answers: list[str] = Field(default_factory=list, max_length=10)
    idempotency_key: str = Field(min_length=8, max_length=200, description="Stable key; retries never duplicate")
    dry_run: bool = Field(default=False, description="Return what would be sent and its cost, without sending")
    meta: dict[str, Any] = Field(default_factory=dict)


class SubmitInput(BaseModel):
    freelancer_id: str = Field(min_length=1, max_length=100)
    proposal_id: str = Field(min_length=1, max_length=100)
    job_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=8, max_length=200)
    dry_run: bool = False


class MessageInput(BaseModel):
    freelancer_id: str = Field(min_length=1, max_length=100)
    thread_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=3000)
    idempotency_key: str = Field(min_length=8, max_length=200)
    dry_run: bool = False


class WriteResult(BaseModel):
    status: Literal["dry_run", "created", "submitted", "sent", "replayed", "error"]
    marketplace: str
    id: str | None = None
    would_send: dict[str, Any] | None = None
    connects_cost: int = 0
    connects_balance_after: int | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


async def _write(ctx, tool: str, key: str, args: dict, do) -> WriteResult:
    user, trace = caller(ctx)
    limiter.check(user)
    scoped = f"{SERVER}:{tool}:{key}"
    prev = await idem_get(scoped)
    if prev:
        res = WriteResult(**{**prev, "status": "replayed"})
        await audit(SERVER, tool, user, trace, args, {"replayed": True})
        return res
    try:
        res = await do()
    except MarketplaceError as e:
        res = WriteResult(status="error", marketplace=get_adapter().name, detail={"status": e.status, "error": str(e.detail)})
        await audit(SERVER, tool, user, trace, args, res.model_dump())
        return res
    await idem_put(scoped, SERVER, res.model_dump())
    await audit(SERVER, tool, user, trace, args, res.model_dump())
    return res


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
async def create_proposal_draft(input: ProposalDraftInput, ctx: Context = None) -> WriteResult:
    """Create a proposal DRAFT on the marketplace (spends no Connects). Use dry_run=true for the approval preview."""
    m = get_adapter()
    job = await m.get_job(input.job_id)
    cost = _connects_cost(job)
    payload = input.model_dump(include={"freelancer_id", "job_id", "cover_letter", "bid_amount", "screening_answers", "meta"})
    if input.dry_run:
        bal = (await m.get_connects_balance(input.freelancer_id)).get("balance")
        return WriteResult(status="dry_run", marketplace=m.name, would_send=payload, connects_cost=cost,
                           connects_balance_after=(bal - cost) if isinstance(bal, int) else None)

    async def do():
        out = await m.create_proposal_draft(payload, input.idempotency_key)
        return WriteResult(status="created", marketplace=m.name, id=out.get("proposal_id"), connects_cost=cost,
                           detail={"status": out.get("status")})

    return await _write(ctx, "create_proposal_draft", input.idempotency_key, input.model_dump(exclude={"cover_letter"}), do)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True))
async def submit_proposal(input: SubmitInput, ctx: Context = None) -> WriteResult:
    """Submit an approved draft. SPENDS CONNECTS. Only call after explicit human approval. Idempotent by key."""
    m = get_adapter()
    job = await m.get_job(input.job_id)
    cost = _connects_cost(job)
    if input.dry_run:
        bal = (await m.get_connects_balance(input.freelancer_id)).get("balance")
        return WriteResult(status="dry_run", marketplace=m.name, id=input.proposal_id, connects_cost=cost,
                           connects_balance_after=(bal - cost) if isinstance(bal, int) else None)

    async def do():
        out = await m.submit_proposal(input.freelancer_id, input.proposal_id, input.idempotency_key)
        bal = (await m.get_connects_balance(input.freelancer_id)).get("balance")
        return WriteResult(status="submitted", marketplace=m.name, id=input.proposal_id,
                           connects_cost=out.get("connects_spent", cost), connects_balance_after=bal,
                           detail={"status": out.get("status"), "note": out.get("note")})

    return await _write(ctx, "submit_proposal", input.idempotency_key, input.model_dump(), do)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True))
async def send_message(input: MessageInput, ctx: Context = None) -> WriteResult:
    """Send an approved message to a client thread. Only call after explicit human approval. Idempotent by key."""
    m = get_adapter()
    if input.dry_run:
        return WriteResult(status="dry_run", marketplace=m.name, id=input.thread_id,
                           would_send={"thread_id": input.thread_id, "text": input.text})

    async def do():
        out = await m.send_message(input.freelancer_id, input.thread_id, input.text, input.idempotency_key)
        return WriteResult(status="sent", marketplace=m.name, id=input.thread_id, detail={"ok": out.get("ok", True)})

    return await _write(ctx, "send_message", input.idempotency_key, input.model_dump(exclude={"text"}), do)


def http_app():
    from mcp_servers.common.guard import BearerAuth

    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuth)
    return app


def main() -> None:
    import uvicorn

    uvicorn.run(http_app(), host="0.0.0.0", port=8102)


if __name__ == "__main__":
    main()
