"""Bid graph (one thread per job).

load_job -> Send(job_analyst | risk_assessor | fit_matcher) in parallel -> decide
  -> skip/watch: END
  -> pricing_strategist -> (not worth Connects: END)
  -> proposal_writer -> verifier -> critic --(fail, < max revisions)--> proposal_writer
                                         --(pass or limit)--> compliance_guard -> (blocked: END)
  -> approval [interrupt()] -> (rejected: END) -> submit -> END
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from agent.mcp_client import MarketplaceDown
from agent.nodes._base import node, tool
from agent.nodes.analyst import job_analyst
from agent.nodes.approval import approval, submit
from agent.nodes.compliance import compliance_guard
from agent.nodes.critic import critic, verifier
from agent.nodes.fit_matcher import fit_matcher
from agent.nodes.pricing import decide, pricing_strategist
from agent.nodes.risk_assessor import risk_assessor
from agent.nodes.writer import ab_arm, proposal_writer
from agent.settings import config
from agent.state import BidState


@node("load_job")
async def load_job(state: dict) -> dict:
    out: dict = {"strategy": state.get("strategy") or ab_arm(state["job_id"])}
    if not state.get("job"):
        try:
            job, t = await tool(state, "scout", "get_job", {"job_id": state["job_id"]})
        except MarketplaceDown as e:
            return {"status": "waiting_marketplace", "errors": [str(e)]}
        out.update(job=job, trace=[t])
    out["status"] = "analysing"
    return out


def fan_out(state: dict):
    if state.get("status") in ("waiting_marketplace", "needs_attention"):
        return END
    return [Send("job_analyst", state), Send("risk_assessor", state), Send("fit_matcher", state)]


def after_decide(state: dict) -> str:
    return "pricing_strategist" if state.get("decision", {}).get("action") == "bid" and not state.get("status") in (
        "skipped", "watch", "waiting_marketplace", "needs_attention") else END


def after_pricing(state: dict) -> str:
    return END if state.get("status") in ("skipped", "waiting_marketplace", "needs_attention") else "proposal_writer"


def after_critic(state: dict) -> str:
    if state.get("status") == "needs_attention":
        return END
    c = state.get("critique", {})
    if not c.get("passed") and state.get("revisions", 0) < config().budgets["max_revisions"]:
        return "proposal_writer"
    return "compliance_guard"


def after_compliance(state: dict) -> str:
    return END if state.get("status") in ("blocked", "needs_attention") else "approval"


def after_approval(state: dict) -> str:
    return END if state.get("status") in ("rejected", "blocked", "needs_attention") else "submit"


def build_bid_graph(checkpointer=None, store=None):
    g = StateGraph(BidState)
    retry = RetryPolicy(max_attempts=3, initial_interval=1.0, retry_on=lambda e: not isinstance(e, (KeyError, TypeError)))
    g.add_node("load_job", load_job, retry_policy=retry)
    g.add_node("job_analyst", job_analyst, retry_policy=retry)
    g.add_node("risk_assessor", risk_assessor, retry_policy=retry)
    g.add_node("fit_matcher", fit_matcher, retry_policy=retry)
    g.add_node("decide", decide)
    g.add_node("pricing_strategist", pricing_strategist, retry_policy=retry)
    g.add_node("proposal_writer", proposal_writer, retry_policy=retry)
    g.add_node("verifier", verifier, retry_policy=retry)
    g.add_node("critic", critic, retry_policy=retry)
    g.add_node("compliance_guard", compliance_guard)
    g.add_node("approval", approval)
    g.add_node("submit", submit, retry_policy=retry)

    g.add_edge(START, "load_job")
    g.add_conditional_edges("load_job", fan_out, ["job_analyst", "risk_assessor", "fit_matcher", END])
    g.add_edge(["job_analyst", "risk_assessor", "fit_matcher"], "decide")
    g.add_conditional_edges("decide", after_decide, ["pricing_strategist", END])
    g.add_conditional_edges("pricing_strategist", after_pricing, ["proposal_writer", END])
    g.add_edge("proposal_writer", "verifier")
    g.add_edge("verifier", "critic")
    g.add_conditional_edges("critic", after_critic, ["proposal_writer", "compliance_guard", END])
    g.add_conditional_edges("compliance_guard", after_compliance, ["approval", END])
    g.add_conditional_edges("approval", after_approval, ["submit", END])
    g.add_edge("submit", END)
    return g.compile(checkpointer=checkpointer, store=store)
