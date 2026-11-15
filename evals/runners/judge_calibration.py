"""LLM judge + calibration against human labels (B4).

Step 1 (Claude/automatic): python -m evals.runners.judge_calibration --prepare
   scores 30 proposals from evals/results/agent_*.json with the LLM judge (prompt: agent/prompts/judge.md) and writes
   evals/datasets/judge_labels.csv with an empty `human_score` column (judge score hidden from the labeller file).
Step 2 (human): fill `human_score` (1-5) for all 30 rows using the rubric in agent/prompts/judge.md.
Step 3: python -m evals.runners.judge_calibration --kappa   -> evals/results/judge_calibration.json
   (quadratic-weighted Cohen's kappa + the largest disagreements for the viva).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys

from pydantic import BaseModel, Field

from agent.settings import ROOT
from evals.runners.common import gigsim_jobs, save

SHEET = ROOT / "evals" / "datasets" / "judge_labels.csv"
JUDGE = ROOT / "evals" / "datasets" / "judge_scores.json"


class Judgement(BaseModel):
    score: int = Field(ge=1, le=5)
    reason: str = ""


def qwk(a: list[int], b: list[int], k: int = 5) -> float:
    import numpy as np

    o = np.zeros((k, k))
    for x, y in zip(a, b, strict=True):
        o[x - 1][y - 1] += 1
    w = np.array([[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)])
    e = np.outer(o.sum(1), o.sum(0)) / o.sum()
    return float(1 - (w * o).sum() / (w * e).sum()) if (w * e).sum() else 1.0


async def prepare() -> None:
    from agent.llm import llm_json
    from agent.nodes.analyst import job_text

    props = []
    for p in sorted((ROOT / "evals" / "results").glob("agent_*.json")):
        props += [dict(x, source=p.stem) for x in json.loads(p.read_text(encoding="utf-8")).get("proposals_detail", [])]
    seen, picked = set(), []
    for x in props:  # diverse sample: unique texts across runs
        if x["text"] not in seen:
            seen.add(x["text"])
            picked.append(x)
    picked = picked[:30]
    jobs = gigsim_jobs()
    scores = {}
    with open(SHEET, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["row", "job_id", "job_title", "proposal", "human_score"])
        for i, x in enumerate(picked):
            j, u = await llm_json("judge", "judge", Judgement, lambda: Judgement(score=3, reason="heuristic"),
                                  job=job_text(jobs[x["job_id"]]), draft=x["text"])
            await asyncio.sleep(9)  # free-tier tokens-per-minute window
            scores[i] = {"judge": j.score, "reason": j.reason, "model": u.model, "source": x["source"]}
            wr.writerow([i, x["job_id"], jobs[x["job_id"]]["title"], x["text"], ""])
    JUDGE.write_text(json.dumps(scores, indent=1), encoding="utf-8")
    print(f"wrote {SHEET} ({len(picked)} rows); judge scores in {JUDGE}")


def kappa() -> None:
    rows = list(csv.DictReader(open(SHEET, encoding="utf-8")))
    judge = json.loads(JUDGE.read_text(encoding="utf-8"))
    pairs = [(int(r["human_score"]), judge[r["row"]]["judge"], r) for r in rows if r["human_score"].strip()]
    if len(pairs) < 10:
        sys.exit(f"only {len(pairs)} human labels; fill human_score in {SHEET}")
    h, j = [p[0] for p in pairs], [p[1] for p in pairs]
    dis = sorted(pairs, key=lambda p: -abs(p[0] - p[1]))[:3]
    save("judge_calibration", {"n": len(pairs), "quadratic_weighted_kappa": round(qwk(h, j), 3),
                               "exact_agreement": round(sum(a == b for a, b in zip(h, j, strict=True)) / len(pairs), 3),
                               "mean_human": round(sum(h) / len(h), 2), "mean_judge": round(sum(j) / len(j), 2),
                               "largest_disagreements": [{"row": r["row"], "job": r["job_title"], "human": a, "judge": b,
                                                          "judge_reason": judge[r["row"]]["reason"]} for a, b, r in dis]})
    print("kappa", round(qwk(h, j), 3))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--kappa", action="store_true")
    a = ap.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(prepare()) if a.prepare else kappa()
