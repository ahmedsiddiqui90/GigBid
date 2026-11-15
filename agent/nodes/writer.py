"""Proposal Writer: cover letter + screening answers citing evidence. MCP: portfolio read."""
from __future__ import annotations

import random
import re

from agent.handoffs import ProposalDraft
from agent.llm import llm_json
from agent.mcp_client import MarketplaceDown
from agent.memory.store import style_rules
from agent.nodes._base import node, tool, usage
from agent.nodes.analyst import job_text
from agent.nodes.pricing import _store
from agent.safety.untrusted import strip_injection, wrap
from agent.settings import config


def ab_arm(job_id: str) -> str:
    arms = config().experiments["ab_test"]["arms"]
    return random.Random(job_id).choice(arms) if config().experiments["ab_test"]["enabled"] else arms[0]


def outcome_of(e: dict) -> str | None:
    s = e.get("snippet", "")
    for pat in (r"\*\*Outcome\.\*\*\s*The project (.+?)\.(?:\s|$)", r"Result in production:\s*(.+?)\.(?:\s|$)",
                r"the work (.+?)\.(?:\s|$)"):
        m = re.search(pat, s)
        if m:
            return m.group(1).strip()
    return None


def heuristic_draft(state: dict, evidence: list[dict], style: list[str], critique: dict | None) -> ProposalDraft:
    job = state["job"]
    reqs = state.get("job_spec", {}).get("requirements") or job.get("skills", [])
    strategy = state.get("strategy", "evidence_first")
    strong, projects = [], set()
    for e in evidence:  # one item per project, best types first
        if e["type"] in ("case_study", "readme", "review") and outcome_of(e) and e.get("project") not in projects:
            projects.add(e.get("project"))
            strong.append(e)
    strong = strong[:2]
    title = re.sub(r"\s+for .*$", "", job.get("title", "your project")).strip()
    lines = []
    if strategy == "question_first":
        lines.append(f"What matters most for your {title.lower()}: shipping fast, or making it easy to maintain later?")
    else:
        lines.append(f"Your {title.lower()} needs {', '.join(reqs[:3])} done properly, with something you can maintain after handover.")
    for e in strong:
        proj = (e.get("project") or e.get("title", "similar")).replace("_", " ")
        lines.append(f"In a similar {proj} project for a past client, the work {outcome_of(e)} [{e['id']}].")
    if not strong and evidence:
        lines.append(f"My portfolio item '{evidence[0]['title']}' is the closest match [{evidence[0]['id']}].")
    lines.append(f"I would start with a short call to confirm scope and success criteria, then deliver in weekly "
                 f"milestones covering {', '.join(reqs[:4])}, with tests, documentation and a recorded handover at the end. "
                 f"You will see a working version in the first week, so feedback shapes the rest of the work.")
    if critique and any("short" in i.lower() for i in critique.get("issues", [])):
        lines.append("You will get a working version early so you can give feedback before the final delivery.")
    text = " ".join(lines)
    if any("exclamation" in r for r in style):
        text = text.replace("!", ".")
    answers = []
    for i, _q in enumerate(job.get("screening_questions", [])):
        e = strong[i % len(strong)] if strong else (evidence[0] if evidence else None)
        if e:
            proj = (e.get("project") or "similar").replace("_", " ")
            answers.append(f"Yes. In my {proj} project the work {outcome_of(e) or 'was delivered to the client'} [{e['id']}].")
        else:
            answers.append("I have not done this exact work before; I can walk you through my approach on a call.")
    return ProposalDraft(cover_letter=text, screening_answers=answers, cited_ids=[e["id"] for e in strong])


@node("proposal_writer")
async def proposal_writer(state: dict) -> dict:
    job = state["job"]
    evidence = {e["id"]: e for e in state.get("evidence", [])}
    trace = []
    try:  # targeted retrieval per extracted requirement (JobSpec from the analyst)
        for r in (state.get("job_spec", {}).get("requirements") or [])[:4]:
            res, t = await tool(state, "proposal_writer", "search_evidence",
                                {"requirement": r, "k": 3, "filters": {"persona": state["persona"]}})
            trace.append(t)
            for e in res.get("items", []):
                evidence.setdefault(e["id"], {**e, "project": e.get("source_project")})
    except MarketplaceDown:
        pass  # writing can proceed with the fit evidence we already have
    ev = sorted(evidence.values(), key=lambda e: e["type"] == "proposal")[:8]
    rules = await style_rules(_store(), str(state.get("user_id")))
    critique = state.get("critique")  # present only after the Critic sent the draft back
    ev_block = "\n".join(f"[{e['id']}] ({e['type']}) {e['title']}: {e['snippet'][:450]}" for e in ev)
    clean_job = {**job, "description": strip_injection(job.get("description", ""))}
    draft, u = await llm_json(
        "proposal_writer", "proposal_writer", ProposalDraft, lambda: heuristic_draft(state, ev, rules, critique),
        job=wrap(job_text(clean_job)), persona=f"{state['persona']} at ${state.get('hourly_rate')}/h",
        price=f"${state.get('price', {}).get('amount')}", evidence=ev_block,
        style_rules="\n".join(f"- {r}" for r in rules) or "(none yet)",
        critique="\n".join(f"- {i}" for i in (critique or {}).get("issues", [])) or "(first draft)",
        strategy=config().experiments["ab_test"]["arms"] and state.get("strategy", "evidence_first"))
    draft.cited_ids = sorted(set(re.findall(r"\[([a-z]{2,4}-[\w-]+)\]", draft.cover_letter + " ".join(draft.screening_answers))))
    return {"draft": draft.model_dump(), "evidence": list(evidence.values()), "usage": usage(u), "trace": trace,
            "revisions": state.get("revisions", 0) + (1 if critique else 0)}
