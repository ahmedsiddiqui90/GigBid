"""Fit Matcher: map each requirement to portfolio evidence; fit score with reasons. MCP: portfolio read."""
from __future__ import annotations

import re

from agent.handoffs import FitReport, RequirementMatch
from agent.mcp_client import MarketplaceDown
from agent.nodes._base import node, tool
from agent.nodes.analyst import heuristic_spec

GENERIC = {"developer", "engineer", "expert", "specialist", "project", "need", "needed", "help", "build", "looking",
           "freelancer", "job", "work", "experienced", "senior", "junior", "website", "app", "application", "the", "and",
           "for", "with", "consultant", "required", "remote", "opportunity", "long", "term", "company", "business"}


def covers(requirement: str, ev: dict) -> bool:
    r = requirement.lower().strip()
    skills = [s.lower() for s in ev.get("skills", [])]
    if any(r == s or (len(r) > 3 and (r in s or s in r)) for s in skills):
        return True
    words = [w for w in re.findall(r"[a-z0-9+#.]{3,}", r) if w not in GENERIC]
    text = (ev.get("snippet", "") + " " + " ".join(skills)).lower()
    return bool(words) and sum(w in text for w in words) / len(words) >= 0.75


def score_fit(reqs: list[str], per_req: dict[str, list[dict]]) -> FitReport:
    matrix = []
    for r in reqs:
        evs = per_req.get(r, [])
        ok = [e["id"] for e in evs if covers(r, e)]
        matrix.append(RequirementMatch(requirement=r, evidence_ids=ok[:3] or [e["id"] for e in evs[:1]], covered=bool(ok)))
    covered = sum(m.covered for m in matrix)
    score = covered / len(matrix) if matrix else 0.0
    reasons = [f"{covered}/{len(matrix)} requirements have direct portfolio evidence"]
    if len(matrix) < 3:  # too few explicit requirements to be confident about fit
        score *= len(matrix) / 3
        reasons.append("fewer than 3 explicit requirements: fit discounted")
    missing = [m.requirement for m in matrix if not m.covered]
    if missing:
        reasons.append("no evidence for: " + ", ".join(missing[:4]))
    return FitReport(score=round(score, 2), matrix=matrix, reasons=reasons)


@node("fit_matcher")
async def fit_matcher(state: dict) -> dict:
    job = state["job"]
    reqs = (job.get("skills") or heuristic_spec(job).requirements)[:6]
    per_req: dict[str, list[dict]] = {}
    trace, evidence = [], {}
    try:
        for r in reqs:
            res, t = await tool(state, "fit_matcher", "search_evidence",
                                {"requirement": f"{r} ({job.get('title', '')})", "k": 4,
                                 "filters": {"persona": state["persona"], "variant": state.get("retrieval_variant")}})
            trace.append(t)
            per_req[r] = res.get("items", [])
            for e in per_req[r]:
                evidence.setdefault(e["id"], {**e, "project": e.get("source_project")})
    except MarketplaceDown as e:
        return {"degraded": [str(e)], "errors": [str(e)], "trace": trace}
    fit = score_fit(reqs, per_req)
    return {"fit": fit.model_dump(), "evidence": list(evidence.values()), "trace": trace}
