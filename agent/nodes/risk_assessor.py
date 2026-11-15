"""Risk Assessor: client quality + scam / free-work / off-platform / injection flags. MCP: marketplace read."""
from __future__ import annotations

import re

from agent.handoffs import RiskReport
from agent.llm import llm_json
from agent.mcp_client import MarketplaceDown
from agent.nodes._base import node, tool, usage
from agent.nodes.analyst import job_text
from agent.safety.untrusted import injection_hits, scam_hits, wrap


def rule_risk(job: dict, client: dict | None) -> RiskReport:
    text = f"{job.get('title', '')}\n{job.get('description', '')}"
    flags, score, notes = [], 0.0, []
    scams = scam_hits(text)
    if scams:
        flags.append("scam_signals")
        score += 0.45 + 0.15 * min(len(scams) - 1, 2)
    if re.search(r"(?i)\b(unpaid|for free|free (test|trial|sample))\b", text):
        flags.append("free_work")
        score += 0.3
    if re.search(r"(?i)(telegram|whats ?app|skype|outside (of )?(the )?platform|off[- ]platform)", text):
        flags.append("off_platform")
        score += 0.2
    budget = (job.get("budget") or {}).get("max") or 0
    if budget <= 0:
        flags.append("no_budget")
        score += 0.2
    inj = [s for s in re.split(r"(?<=[.!?\n])\s+", job.get("description", "")) if injection_hits(s)]
    if inj:
        flags.append("injection")  # defended by ignoring; not by itself a reason to skip
        score += 0.1
    if client:
        if not client.get("payment_verified"):
            flags.append("unverified_payment")
            score += 0.15
        if client.get("hires", 0) == 0:
            flags.append("no_hire_history")
            score += 0.1
        if client.get("avg_rating") is not None and client["avg_rating"] < 4.0:
            flags.append("poor_client_rating")
            score += 0.1
        notes.append(f"client: verified={client.get('payment_verified')} hires={client.get('hires')} "
                     f"spend=${client.get('total_spend')} rating={client.get('avg_rating')}")
    return RiskReport(score=min(1.0, round(score, 2)), flags=flags, injection_text=inj,
                      explanation="; ".join(notes + [f"rule flags: {', '.join(flags) or 'none'}"]),
                      client_summary=notes[0] if notes else "")


@node("risk_assessor")
async def risk_assessor(state: dict) -> dict:
    job = state["job"]
    trace = []
    client = None
    try:
        client, t = await tool(state, "risk_assessor", "get_client_history", {"client_id": job["client_id"]})
        trace.append(t)
    except MarketplaceDown as e:
        return {"degraded": [str(e)], "errors": [str(e)], "trace": trace}
    rules = rule_risk(job, client)
    llm, u = await llm_json("risk_assessor", "risk_assessor", RiskReport, lambda: rules,
                            job=wrap(job_text(job)), client=str({k: v for k, v in (client or {}).items() if k != "reviews"}),
                            signals=", ".join(rules.flags) or "none")
    # Rules are authoritative for the score (measurable, injection-proof); the model adds flags/explanation.
    flags = list(dict.fromkeys(rules.flags + [f for f in llm.flags if f in ("scam", "free_work", "off_platform")]))
    bump = 0.1 if ("scam" in llm.flags and "scam_signals" not in rules.flags) else 0.0
    report = RiskReport(score=min(1.0, rules.score + bump), flags=flags, injection_text=rules.injection_text,
                        explanation=(llm.explanation or rules.explanation)[:600], client_summary=rules.client_summary)
    return {"risk": report.model_dump(), "client": client or {}, "usage": usage(u), "trace": trace}
