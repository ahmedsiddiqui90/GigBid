"""Claim verification (before the Critic) and the Critic (max 2 revisions)."""
from __future__ import annotations

import re

from agent.handoffs import Critique
from agent.llm import Usage, llm_json
from agent.nodes._base import node, usage
from agent.nodes.analyst import job_text
from agent.safety.untrusted import wrap
from agent.settings import config, policy
from rag.verify import repair, unsupported_count, verify_claims


@node("verifier")
async def verifier(state: dict) -> dict:
    d = dict(state["draft"])
    ev = state.get("evidence", [])
    texts = [d["cover_letter"]] + list(d.get("screening_answers", []))
    before, after, all_checks, us = 0, 0, [], []
    fixed = []
    for t in texts:
        checks, u = await verify_claims(t, ev)
        us.append(u)
        before += unsupported_count(checks)
        rt = repair(t, checks, ev)
        fixed.append(rt)
        all_checks += [c.model_dump() for c in checks]
    d["cover_letter"], d["screening_answers"] = fixed[0], fixed[1:]
    # Residual check without a second LLM pass (saves verifier tokens): an unsupported claim still present in the
    # repaired text counts as unsupported "after".
    joined = " ".join(fixed).lower()
    after = sum(c["label"] == "unsupported" and c["claim"].lower() in joined for c in all_checks)
    d["cited_ids"] = sorted(set(re.findall(r"\[([a-z]{2,4}-[\w-]+)\]", " ".join(fixed))))
    return {"draft": d, "verification": {"unsupported_before": before, "unsupported_after": after, "checks": all_checks},
            "usage": [x.dict() for x in us]}


def heuristic_critique(state: dict) -> Critique:
    d = state["draft"]
    text = d["cover_letter"]
    issues, score = [], 1.0
    words = len(text.split())
    if words < 90:
        issues.append(f"Too short ({words} words); add a concrete plan or result.")
        score -= 0.2
    if words > 240:
        issues.append(f"Too long ({words} words); cut to under 220.")
        score -= 0.2
    if any(re.search(p, text) for p in policy()["proposal"]["generic_openings"]):
        issues.append("Generic opening; start with the client's specific problem.")
        score -= 0.3
    if len(d.get("cited_ids", [])) < 2:
        issues.append("Fewer than two evidence citations; cite specific portfolio items.")
        score -= 0.2
    must = state["job"].get("skills", [])[:2]
    if must and not any(m.lower() in text.lower() for m in must):
        issues.append(f"Does not mention the key requirements ({', '.join(must)}).")
        score -= 0.2
    if state.get("verification", {}).get("unsupported_after", 0):
        issues.append("Contains unsupported claims; remove them.")
        score -= 0.3
    if len(d.get("screening_answers", [])) < len(state["job"].get("screening_questions", [])):
        issues.append("Answer every screening question.")
        score -= 0.2
    score = max(0.0, round(score, 2))
    return Critique(score=score, passed=score >= config().thresholds["critic_pass"], issues=issues)


@node("critic")
async def critic(state: dict) -> dict:
    rules = heuristic_critique(state)
    c, u = await llm_json("critic", "critic", Critique, lambda: rules, job=wrap(job_text(state["job"])),
                          draft=state["draft"]["cover_letter"] + "\n\nScreening answers:\n" + "\n".join(state["draft"].get("screening_answers", [])),
                          verification=str({k: v for k, v in state.get("verification", {}).items() if k != "checks"}),
                          threshold=config().thresholds["critic_pass"])
    # Hard checks always count, whatever the model says.
    hard = [i for i in rules.issues if "unsupported" in i or "Generic" in i]
    issues = list(dict.fromkeys(hard + c.issues))[:6]
    score = min(c.score, rules.score) if hard else c.score
    passed = score >= config().thresholds["critic_pass"] and not hard
    return {"critique": Critique(score=score, passed=passed, issues=issues).model_dump(), "usage": usage(u)}


def no_llm_usage(node: str) -> Usage:
    return Usage(node, "rules")
