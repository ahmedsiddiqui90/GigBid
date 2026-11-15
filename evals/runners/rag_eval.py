"""Retrieval evaluation (B4) + ablation (R&D question B). No LLM needed.

Recall@5, MRR and nDCG@10 against gold evidence items, per variant, persona and job kind.
Hypothesis (stated before running): requirement decomposition + hybrid retrieval raises evidence Recall@5
by >= 10 points over V0 on jobs with 4+ requirements.
Run: python -m evals.runners.rag_eval
"""
from __future__ import annotations

import math
import time
from collections import defaultdict

from evals.runners.common import dev_labels, gigsim_jobs, save
from rag.index.store import load_index
from rag.retriever import VARIANTS, get_variant
from rag.variants.pipeline import ablate, retrieve

HYPOTHESIS = ("Requirement decomposition + hybrid BM25/dense retrieval (V2) raises evidence Recall@5 by at least "
              "10 points over V0 on jobs with 4+ requirements.")


def metrics(ranked: list[str], gold: set[str]) -> dict:
    r5 = len(set(ranked[:5]) & gold) / min(len(gold), 5)
    mrr = next((1 / (i + 1) for i, x in enumerate(ranked) if x in gold), 0.0)
    dcg = sum(1 / math.log2(i + 2) for i, x in enumerate(ranked[:10]) if x in gold)
    idcg = sum(1 / math.log2(i + 2) for i in range(min(len(gold), 10)))
    return {"recall@5": r5, "mrr": mrr, "ndcg@10": dcg / idcg if idcg else 0.0}


def query_of(job: dict) -> dict:
    return {"text": f"{job['title']}\n{job['description']}", "requirements": job.get("skills", []), "title": job["title"]}


def run_variant(fn, labels, jobs) -> dict:
    per = defaultdict(list)
    lat = []
    for lab in labels:
        job = jobs[lab["job_id"]]
        t0 = time.perf_counter()
        ranked = [e["id"] for e in fn(load_index(lab["persona"]), query_of(job))]
        lat.append(time.perf_counter() - t0)
        m = metrics(ranked, set(lab["gold_evidence"]))
        for key in ("all", f"persona:{lab['persona']}", f"kind:{lab['kind']}",
                    "reqs>=4" if lab["n_requirements"] >= 4 else "reqs<4"):
            per[key].append(m)
    agg = {k: {m: round(sum(x[m] for x in v) / len(v), 3) for m in ("recall@5", "mrr", "ndcg@10")} | {"n": len(v)}
           for k, v in per.items()}
    agg["latency_ms_mean"] = round(1000 * sum(lat) / len(lat), 1)
    return agg


def main() -> None:
    labels = [x for x in dev_labels() if x["gold_evidence"]]
    jobs = gigsim_jobs()
    results = {}
    for v in VARIANTS:
        mod = get_variant(v)
        results[v] = run_variant(lambda idx, q, m=mod: m.retrieve(idx, q, 10), labels, jobs)
        print(v, results[v]["all"])
    # E5 optimisation check: rerank top-30 vs top-12 (quality and latency).
    from agent.settings import config

    keep = config().retrieval.get("rerank_top")
    config().retrieval["rerank_top"] = 30
    results["v3_rerank_top30"] = run_variant(lambda idx, q: get_variant("v3_rerank").retrieve(idx, q, 10), labels, jobs)
    config().retrieval["rerank_top"] = keep
    print("v3 top30", results["v3_rerank_top30"]["all"], results["v3_rerank_top30"]["latency_ms_mean"])
    # Ablation: remove one component at a time from the best preset (V4 = decompose+hybrid+rerank+outcome).
    ablation = {}
    for sw in ("decompose", "hybrid", "rerank", "outcome"):
        s = ablate("v4_outcome", sw)
        ablation[f"v4 without {sw}"] = run_variant(lambda idx, q, s=s: retrieve(idx, q, 10, s), labels, jobs)["all"]
        print("ablate", sw, ablation[f"v4 without {sw}"])
    best = max(VARIANTS, key=lambda v: (results[v]["all"]["recall@5"], results[v]["all"]["ndcg@10"]))
    d = results["v2_hybrid"].get("reqs>=4", {}).get("recall@5", 0) - results["v0_naive"].get("reqs>=4", {}).get("recall@5", 0)
    save("rag_eval", {"hypothesis": HYPOTHESIS, "hypothesis_delta_recall5_reqs>=4": round(d, 3),
                      "hypothesis_supported": d >= 0.10, "n_jobs": len(labels), "variants": results,
                      "ablation": ablation, "best_by_recall5": best})
    print("best:", best, "hypothesis delta:", round(d, 3))


if __name__ == "__main__":
    main()
