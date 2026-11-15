"""Compliance Guard: enforce agent/policy.yaml on drafts (strip contacts/guarantees, block free work and
fabrication, remove anything an injected instruction asked for). No MCP access, no LLM: deterministic."""
from __future__ import annotations

import re

from agent.handoffs import ComplianceVerdict
from agent.nodes._base import node
from agent.settings import policy


def injected_tokens(injection_text: list[str]) -> list[str]:
    """Unusual tokens an injection asked to include (e.g. canary words, quoted phrases, emails)."""
    toks = []
    for s in injection_text:
        toks += re.findall(r"\b[A-Z][A-Z0-9]{4,}\b", s)
        toks += [a or b for a, b in re.findall(r"'([^']{3,40})'|\"([^\"]{3,40})\"", s)]
        toks += re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", s)
    return [t for t in toks if t and t.upper() not in ("IMPORTANT", "NOTE", "SYSTEM")]


def check_text(text: str, risk: dict, verification: dict | None) -> tuple[str, ComplianceVerdict]:
    edits, blocked, reason = [], False, ""
    out = text
    for rule in policy()["rules"]:
        pats = rule.get("patterns", [])
        if rule["action"] == "strip":
            for p in pats:
                if re.search(p, out):
                    out = re.sub(p, "", out)
                    edits.append(f"{rule['id']}: removed text matching policy")
        elif rule["action"] == "block":
            for p in pats:
                if re.search(p, out):
                    blocked, reason = True, f"{rule['id']}: {rule['description']}"
        elif rule["action"] == "block_if_unsupported" and verification and verification.get("unsupported_after", 0) > 0:
            blocked, reason = True, f"{rule['id']}: {verification['unsupported_after']} unsupported claim(s) remain"
    for tok in injected_tokens(risk.get("injection_text", [])):
        if tok.lower() in out.lower():
            out = re.sub(re.escape(tok), "", out, flags=re.I)
            edits.append(f"injection_defence: removed '{tok}' requested by text inside the job post")
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out, ComplianceVerdict(passed=not blocked, blocked=blocked, reason=reason, edits=edits)


@node("compliance_guard")
async def compliance_guard(state: dict) -> dict:
    d = dict(state["draft"])
    risk = state.get("risk", {})
    letter, v = check_text(d["cover_letter"], risk, state.get("verification"))
    answers, all_edits = [], list(v.edits)
    for a in d.get("screening_answers", []):
        fixed, va = check_text(a, risk, None)
        answers.append(fixed)
        all_edits += va.edits
        if va.blocked:
            v.blocked, v.passed, v.reason = True, False, va.reason
    d["cover_letter"], d["screening_answers"] = letter, answers
    v.edits = all_edits
    out = {"draft": d, "compliance": v.model_dump()}
    if v.blocked:
        out["status"] = "blocked"
    return out
