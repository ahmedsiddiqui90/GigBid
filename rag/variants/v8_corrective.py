"""V8 corrective RAG as a small LangGraph subgraph.

retrieve (V3) -> grade each requirement's best evidence -> weak? rewrite the query and retry once ->
still weak? mark the requirement "no evidence" so the writer must not claim it.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from rag.index.store import PersonaIndex
from rag.variants.pipeline import PRESETS
from rag.variants.pipeline import retrieve as _retrieve

SWITCHES = PRESETS["v3_rerank"]
GRADE_MIN = -4.0  # cross-encoder logit; a requirement whose best hit is below this has no evidence
DROP_BELOW = -9.0  # evidence this irrelevant is never shown to the writer

SYNONYMS = {
    "background jobs": "Celery task queue", "dashboard": "Power BI Tableau Looker report", "llm": "LangChain RAG agent",
    "payments": "Stripe billing subscriptions", "forecast": "time series Prophet forecasting",
    "chatbot": "RAG assistant LangChain", "etl": "Airflow pipelines", "api": "FastAPI GraphQL REST",
}


class CState(TypedDict, total=False):
    idx: PersonaIndex
    job: dict
    k: int
    evidence: list[dict]
    weak: list[str]
    attempt: int
    unsupported_requirements: list[str]


def _retrieve_node(s: CState) -> CState:
    reqs = s["job"].get("requirements", [])
    if s.get("attempt", 0) == 0:
        ev = _retrieve(s["idx"], s["job"], s["k"], SWITCHES)
    else:  # re-query only the weak requirements with expanded wording
        expanded = [r + " " + " ".join(v for k_, v in SYNONYMS.items() if k_ in r.lower()) for r in s["weak"]]
        extra = _retrieve(s["idx"], {**s["job"], "requirements": expanded}, s["k"], SWITCHES)
        have = {e["id"] for e in s["evidence"]}
        ev = s["evidence"] + [e for e in extra if e["id"] not in have]
    del reqs
    return {"evidence": ev, "attempt": s.get("attempt", 0) + 1}


def _grade(s: CState) -> CState:
    reqs = s["job"].get("requirements", []) if s.get("attempt", 1) == 1 else s["weak"]
    best: dict[str, float] = {}
    for e in s["evidence"]:
        r = e.get("requirement")
        if r is not None:
            best[r] = max(best.get(r, -99), e["score"])
    weak = [r for r in reqs if best.get(r, -99) < GRADE_MIN]
    return {"weak": weak}


def _route(s: CState) -> str:
    if s["weak"] and s["attempt"] < 2:
        return "retrieve"
    return "finish"


def _finish(s: CState) -> CState:
    weak = set(s.get("weak", []))
    ev = [e for e in s["evidence"] if e["score"] >= DROP_BELOW]
    ev = sorted(ev, key=lambda e: -e["score"])[: s["k"]]
    return {"evidence": ev, "unsupported_requirements": sorted(weak)}


def _build():
    g = StateGraph(CState)
    g.add_node("retrieve", _retrieve_node)
    g.add_node("grade", _grade)
    g.add_node("finish", _finish)
    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", _route, {"retrieve": "retrieve", "finish": "finish"})
    g.add_edge("finish", END)
    return g.compile()


GRAPH = _build()


def retrieve_with_report(idx: PersonaIndex, job: dict, k: int = 5) -> tuple[list[dict], list[str]]:
    out = GRAPH.invoke({"idx": idx, "job": job, "k": k, "attempt": 0})
    return out["evidence"], out.get("unsupported_requirements", [])


def retrieve(idx: PersonaIndex, job: dict, k: int = 5, candidates: int = 30) -> list[dict]:
    return retrieve_with_report(idx, job, k)[0]
