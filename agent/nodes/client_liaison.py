"""Client Liaison (conversation graph): classify intent, draft reply / interview slots, approval, send.
MCP: marketplace read + write-after-approval, workspace."""
from __future__ import annotations

import hashlib

from langgraph.types import interrupt

from agent.handoffs import LiaisonOutput
from agent.llm import llm_json
from agent.mcp_client import MarketplaceDown
from agent.nodes._base import node, tool, usage
from agent.nodes.compliance import check_text
from agent.safety.untrusted import scam_hits, wrap


def heuristic_liaison(thread: dict) -> LiaisonOutput:
    last = [m for m in thread.get("messages", []) if m["from"] == "client"][-1]["text"]
    low = last.lower()
    if scam_hits(last):
        return LiaisonOutput(intent="scam_signal", reply="Thanks for getting back to me. I keep all communication and "
                             "payment on the platform, so let's continue here. Happy to answer any questions about the project.")
    if any(w in low for w in ("interview", "call", "free for", "available")):
        return LiaisonOutput(intent="interview_request", offer_slots=True,
                             reply="Thank you, I'd be glad to talk. Here are times that work for me:")
    if any(w in low for w in ("budget", "could you do it for", "price", "discount", "cheaper")):
        return LiaisonOutput(intent="negotiation", reply="Thanks for being upfront about the budget. I can reduce the "
                             "scope to the core deliverables to meet that number, or keep the full scope at the original price. "
                             "Which would you prefer?")
    return LiaisonOutput(intent="question", reply="Good question. In week one I would review your current setup, agree "
                         "the exact scope with you, and deliver a first working version you can test, with a short "
                         "written update at the end of the week.")


@node("load_thread")
async def load_thread(state: dict) -> dict:
    try:
        res, t = await tool(state, "client_liaison", "list_messages", {"freelancer_id": state["freelancer_id"]})
    except MarketplaceDown as e:
        return {"status": "waiting_marketplace", "errors": [str(e)]}
    th = next((x for x in res.get("threads", []) if x["thread_id"] == state["thread_id"]), None)
    if not th:
        return {"status": "needs_attention", "errors": ["thread not found"], "trace": [t]}
    return {"thread": th, "trace": [t]}


@node("client_liaison")
async def client_liaison(state: dict) -> dict:
    th = state["thread"]
    convo = "\n".join(f"{m['from']}: {m['text']}" for m in th.get("messages", []))
    out, u = await llm_json("client_liaison", "client_liaison", LiaisonOutput, lambda: heuristic_liaison(th),
                            thread=wrap(convo, "client conversation"), persona=state["persona"],
                            slots="(will be added after classification)")
    # Rule-based scam detection overrides the model (measurable and injection-proof).
    if scam_hits([m for m in th["messages"] if m["from"] == "client"][-1]["text"]):
        out = heuristic_liaison(th)
    trace, slots = [], []
    if out.intent == "interview_request" or out.offer_slots:
        try:
            res, t = await tool(state, "client_liaison", "free_slots", {"days_ahead": 5, "duration_minutes": 30, "max_slots": 3})
            slots = res.get("slots", [])
            trace.append(t)
        except Exception as e:  # noqa: BLE001 - workspace down: reply without slots
            trace.append({"tool": "free_slots", "error": str(e)[:200]})
    reply = out.reply
    if slots:
        reply += "\n" + "\n".join(f"- {s['start'][:16].replace('T', ' ')} UTC" for s in slots)
    return {"intent": out.intent, "reply": reply, "slots": slots, "usage": usage(u), "trace": trace}


@node("conversation_compliance")
async def conversation_compliance(state: dict) -> dict:
    fixed, v = check_text(state["reply"], {}, None)
    return {"reply": fixed, "compliance": v.model_dump(), **({"status": "blocked"} if v.blocked else {})}


@node("message_approval")
async def message_approval(state: dict) -> dict:
    ans = interrupt({"kind": "message", "thread_id": state["thread_id"], "thread": state["thread"],
                     "intent": state["intent"], "reply": state["reply"], "slots": state.get("slots", []),
                     "compliance": state.get("compliance")})
    action = (ans or {}).get("action")
    if action == "reject":
        return {"status": "rejected", "approval": {"action": "reject", "reason": ans.get("reason", "")}}
    if action == "edit":
        fixed, v = check_text(ans.get("text") or state["reply"], {}, None)
        if v.blocked:
            return {"status": "blocked", "compliance": v.model_dump()}
        return {"reply": fixed, "approval": {"action": "edit", "before": state["reply"], "after": fixed}}
    return {"approval": {"action": "approve"}}


@node("send_reply")
async def send_reply(state: dict) -> dict:
    n_msgs = len(state["thread"].get("messages", []))
    key = hashlib.sha256(f"{state['user_id']}:{state['thread_id']}:{n_msgs}:{state['reply']}".encode()).hexdigest()[:20]
    trace = []
    try:
        res, t = await tool(state, "client_liaison", "send_message", {"input": {
            "freelancer_id": state["freelancer_id"], "thread_id": state["thread_id"], "text": state["reply"],
            "idempotency_key": "msg-" + key}})
        trace.append(t)
        if state.get("slots") and state.get("intent") == "interview_request":
            s = state["slots"][0]
            _, t2 = await tool(state, "client_liaison", "create_tentative_hold", {"input": {
                "start": s["start"], "duration_minutes": 30, "title": f"Interview hold: {state['thread_id']}",
                "idempotency_key": "hold-" + key}})
            trace.append(t2)
    except MarketplaceDown as e:
        return {"status": "waiting_marketplace", "errors": [str(e)], "trace": trace}
    return {"status": "sent", "sent": res, "trace": trace}
