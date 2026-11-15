"""Composable retrieval pipeline. Each variant file (v0_naive.py ... v8_corrective.py) is a preset of
these switches, so ablations just flip one switch at a time.

Input "job" is a dict with: text (full post), requirements (list[str]).
Output: list of evidence dicts (item level) with id, type, project, title, snippet, skills, date,
outcome, score, requirement.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from rag.index.store import PersonaIndex, item_text, reranker


@dataclass(frozen=True)
class Switches:
    decompose: bool = False   # V1: one retrieval per requirement
    hybrid: bool = False      # V2: BM25 + dense with reciprocal rank fusion
    rerank: bool = False      # V3: cross-encoder rerank
    outcome: bool = False     # V4: boost evidence linked to won/replied proposals
    fixed_chunks: bool = False  # V0: naive fixed chunks
    exclude_proposals: bool = True  # proposals are phrasing examples, not experience evidence


def rrf(lists: list[list[tuple[str, float]]], k: int = 60) -> list[tuple[str, float]]:
    agg: dict[str, float] = {}
    for lst in lists:
        for rank, (iid, _) in enumerate(lst):
            agg[iid] = agg.get(iid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(agg.items(), key=lambda x: -x[1])


def _search(idx: PersonaIndex, query: str, sw: Switches, n: int) -> list[tuple[str, float]]:
    if sw.fixed_chunks:
        return idx.dense_fixed(query, n)
    dense = idx.dense_items(query, n)
    if not sw.hybrid:
        return dense
    return rrf([dense, idx.bm25_items(query, n)])[:n]


def _outcome_boost(idx: PersonaIndex) -> dict[str, float]:
    """Projects that appear in won/replied proposals get a boost (learning from what worked)."""
    w = {"won": 0.15, "replied": 0.08}
    proj: dict[str, float] = {}
    for it in idx.items:
        if it["type"] == "proposal" and it.get("project") and it.get("outcome") in w:
            proj[it["project"]] = proj.get(it["project"], 0) + w[it["outcome"]]
    return {it["id"]: min(0.3, proj.get(it.get("project"), 0)) for it in idx.items}


def retrieve(idx: PersonaIndex, job: dict, k: int, sw: Switches, candidates: int = 30) -> list[dict]:
    reqs = [r for r in job.get("requirements", []) if r.strip()]
    queries = reqs if (sw.decompose and reqs) else [job["text"]]
    per_query: list[list[tuple[str, float]]] = []
    for q in queries:
        hits = _search(idx, q if not sw.decompose else f"{q}. {job.get('title', '')}", sw, candidates)
        if sw.exclude_proposals:
            hits = [h for h in hits if idx.by_id[h[0]]["type"] != "proposal"]
        if sw.rerank and hits:
            from agent.settings import config

            hits = hits[: int(config().retrieval.get("rerank_top", 30))]
            docs = [item_text(idx.by_id[i]) for i, _ in hits]
            scores = list(reranker().rerank(q, docs))
            hits = sorted(zip([i for i, _ in hits], scores, strict=False), key=lambda x: -x[1])
        per_query.append(hits)

    if sw.outcome:
        boost = _outcome_boost(idx)
        per_query = [sorted(((i, s + boost.get(i, 0) * (abs(s) + 1)) for i, s in lst), key=lambda x: -x[1])
                     for lst in per_query]

    # Merge: round-robin across requirements so every requirement gets evidence.
    out: list[dict] = []
    seen: set[str] = set()
    depth = 0
    while len(out) < k and any(depth < len(lst) for lst in per_query):
        for qi, lst in enumerate(per_query):
            if depth < len(lst) and len(out) < k:
                iid, score = lst[depth]
                if iid not in seen:
                    seen.add(iid)
                    it = idx.by_id[iid]
                    out.append({"id": iid, "type": it["type"], "project": it.get("project"), "title": it["title"],
                                "snippet": it["text"][:600], "skills": it.get("skills", []), "date": it.get("date"),
                                "outcome": it.get("outcome"), "score": round(float(score), 4),
                                "requirement": queries[qi] if sw.decompose else None})
        depth += 1
    return out


PRESETS = {
    "v0_naive": Switches(fixed_chunks=True),
    "v1_decompose": Switches(decompose=True),
    "v2_hybrid": Switches(decompose=True, hybrid=True),
    "v3_rerank": Switches(decompose=True, hybrid=True, rerank=True),
    "v4_outcome": Switches(decompose=True, hybrid=True, rerank=True, outcome=True),
}


def ablate(base: str, switch: str) -> Switches:
    return replace(PRESETS[base], **{switch: not getattr(PRESETS[base], switch)})
