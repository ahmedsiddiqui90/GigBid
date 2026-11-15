"""Human approval (C5, R4) and submission.

`approval` builds the payload (draft, evidence per claim, risk report, price rationale, dry_run preview)
and calls interrupt(). The UI resumes with {"action": "approve" | "edit" | "reject", "text", "answers",
"reason"}. Edits are diffed into style memory and re-checked by Compliance before anything is sent.
`submit` uses idempotency keys derived from (user, job, draft hash), so a crash/restart around the
submit step can never submit twice or spend Connects twice. Nothing is ever auto-sent.
"""
from __future__ import annotations

import hashlib

from langgraph.types import interrupt

from agent.mcp_client import MarketplaceDown
from agent.memory.store import record_edit
from agent.nodes._base import node, tool
from agent.nodes.compliance import check_text
from agent.nodes.pricing import _store


def draft_key(state: dict) -> str:
    d = state["draft"]
    h = hashlib.sha256((d["cover_letter"] + "|".join(d.get("screening_answers", [])) +
                        str(state.get("price", {}).get("amount"))).encode()).hexdigest()[:16]
    return f"{state.get('user_id')}:{state['job_id']}:{h}"


@node("approval")
async def approval(state: dict) -> dict:
    trace = []
    preview = {}
    try:
        preview, t = await tool(state, "submitter", "create_proposal_draft", {"input": {
            "freelancer_id": state["freelancer_id"], "job_id": state["job_id"],
            "cover_letter": state["draft"]["cover_letter"], "bid_amount": state["price"]["amount"],
            "screening_answers": state["draft"].get("screening_answers", []),
            "idempotency_key": "preview-" + draft_key(state), "dry_run": True}})
        trace.append(t)
    except MarketplaceDown as e:
        preview = {"status": "unavailable", "detail": {"error": str(e)}}
    ev = {e["id"]: e for e in state.get("evidence", [])}
    payload = {
        "kind": "proposal", "job_id": state["job_id"], "job_title": state["job"].get("title"),
        "draft": state["draft"], "evidence": {i: ev[i] for i in state["draft"].get("cited_ids", []) if i in ev},
        "claims": state.get("verification", {}).get("checks", []), "risk": state.get("risk"),
        "price": state.get("price"), "critique": state.get("critique"), "compliance": state.get("compliance"),
        "decision": state.get("decision"), "preview": preview, "strategy": state.get("strategy"),
    }
    answer = interrupt(payload)  # pauses here; state is checkpointed in Postgres
    action = (answer or {}).get("action")
    if action == "reject":
        return {"status": "rejected", "approval": {"action": "reject", "reason": answer.get("reason", "")},
                "preview": preview, "trace": trace}
    if action == "edit":
        before = state["draft"]["cover_letter"]
        after = answer.get("text") or before
        store = _store()
        promoted = await record_edit(store, str(state.get("user_id")), before, after) if store else []
        fixed, verdict = check_text(after, state.get("risk", {}), None)
        answers = answer.get("answers", state["draft"].get("screening_answers", []))
        d = {**state["draft"], "cover_letter": fixed, "screening_answers": answers}
        if verdict.blocked:
            return {"status": "blocked", "draft": d, "compliance": verdict.model_dump(),
                    "approval": {"action": "edit", "blocked": True}}
        return {"draft": d, "compliance": verdict.model_dump(), "preview": preview, "trace": trace,
                "approval": {"action": "edit", "before": before, "after": fixed, "promoted_style_rules": promoted}}
    return {"approval": {"action": "approve"}, "preview": preview, "trace": trace}


@node("submit")
async def submit(state: dict) -> dict:
    key = draft_key(state)
    trace = []
    try:
        created, t1 = await tool(state, "submitter", "create_proposal_draft", {"input": {
            "freelancer_id": state["freelancer_id"], "job_id": state["job_id"],
            "cover_letter": state["draft"]["cover_letter"], "bid_amount": state["price"]["amount"],
            "screening_answers": state["draft"].get("screening_answers", []), "idempotency_key": "draft-" + key,
            "meta": {"strategy": state.get("strategy"), "trace_id": state.get("trace_id")}}})
        trace.append(t1)
        if created.get("status") == "error":
            return {"status": "needs_attention", "errors": [f"draft failed: {created.get('detail')}"], "trace": trace}
        sub, t2 = await tool(state, "submitter", "submit_proposal", {"input": {
            "freelancer_id": state["freelancer_id"], "proposal_id": created["id"], "job_id": state["job_id"],
            "idempotency_key": "submit-" + key}})
        trace.append(t2)
    except MarketplaceDown as e:
        return {"status": "waiting_marketplace", "errors": [str(e)], "trace": trace}
    if sub.get("status") == "error":
        return {"status": "needs_attention", "errors": [f"submit failed: {sub.get('detail')}"], "trace": trace}
    return {"status": "submitted", "submission": {"proposal_id": created["id"], **sub}, "trace": trace}
