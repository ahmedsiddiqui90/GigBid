"""Job Analyst: job post -> JobSpec. No MCP access."""
from __future__ import annotations

import re

from agent.handoffs import JobSpec
from agent.llm import llm_json
from agent.nodes._base import node, usage
from agent.safety.untrusted import strip_injection, wrap


def job_text(job: dict) -> str:
    b = job.get("budget") or {}
    return (f"Title: {job.get('title')}\nBudget: {b.get('type')} {b.get('min')}-{b.get('max')} {b.get('currency', 'USD')}\n"
            f"Skills: {', '.join(job.get('skills', []))}\nScreening questions: {job.get('screening_questions', [])}\n\n"
            f"{job.get('description', '')}")


def heuristic_spec(job: dict) -> JobSpec:
    desc = strip_injection(job.get("description", ""))
    bullets = [b.strip() for b in re.findall(r"^\s*[-*]\s*(.+)$", desc, re.M)]
    reqs = list(dict.fromkeys(job.get("skills", []) + [b for b in bullets if len(b) < 60]))[:7]
    if not reqs:
        reqs = [job.get("title", "")]
    deliv = re.findall(r"(?i)deliverables?:\s*(.+)", desc)
    b = job.get("budget") or {}
    return JobSpec(job_id=job["job_id"], title=job.get("title", ""), category=job.get("category", "other"),
                   requirements=reqs, deliverables=[d.strip() for d in (deliv[0].split(",") if deliv else [])],
                   skills=job.get("skills", []), budget_type=b.get("type", "fixed"), budget_min=b.get("min"),
                   budget_max=b.get("max"), timeline=(re.findall(r"(?i)timeline:\s*(.+)", desc) or [None])[0],
                   screening_questions=job.get("screening_questions", []),
                   hidden_needs=["reliable delivery", "clear communication"])


@node("job_analyst")
async def job_analyst(state: dict) -> dict:
    job = state["job"]
    spec, u = await llm_json("job_analyst", "job_analyst", JobSpec, lambda: heuristic_spec(job),
                             job=wrap(job_text(job)))
    spec.job_id = job["job_id"]
    # Marketplace metadata is trusted; keep it authoritative over the model's reading.
    b = job.get("budget") or {}
    spec.budget_min, spec.budget_max = b.get("min"), b.get("max")
    spec.screening_questions = job.get("screening_questions", []) or spec.screening_questions
    spec.category = job.get("category") or spec.category
    if not spec.requirements:
        spec.requirements = heuristic_spec(job).requirements
    return {"job_spec": spec.model_dump(), "usage": usage(u)}
