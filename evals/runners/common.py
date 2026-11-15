"""Shared helpers for evaluation runners. Dev set only - the held-out split is never read here."""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from agent.settings import ROOT

RESULTS = ROOT / "evals" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)


def test_labels() -> list[dict]:
    """Held-out split: used once, for the final test run only (never for tuning)."""
    return [json.loads(x) for x in (ROOT / "data" / "hidden" / "test.jsonl").read_text().splitlines() if x.strip()]


def test_jobs() -> dict[str, dict]:
    return {j["job_id"]: j for j in json.loads((ROOT / "data" / "hidden" / "jobs.json").read_text(encoding="utf-8"))}


def test_clients() -> dict[str, dict]:
    return {c["client_id"]: c for c in json.loads((ROOT / "data" / "hidden" / "clients.json").read_text(encoding="utf-8"))}


def dev_labels() -> list[dict]:
    return [json.loads(x) for x in (ROOT / "evals" / "datasets" / "dev.jsonl").read_text().splitlines() if x.strip()]


def gigsim_jobs() -> dict[str, dict]:
    return {j["job_id"]: j for j in json.loads((ROOT / "data" / "gigsim" / "jobs.json").read_text(encoding="utf-8"))}


def gigsim_clients() -> dict[str, dict]:
    return {c["client_id"]: c for c in json.loads((ROOT / "data" / "gigsim" / "clients.json").read_text(encoding="utf-8"))}


def profile(persona: str) -> dict:
    return json.loads((ROOT / "data" / "personas" / persona / "profile.json").read_text())


def public_job(j: dict) -> dict:
    from gigsim.app import connects_cost

    out = {k: v for k, v in j.items() if k not in ("target_persona", "split", "duplicate_of")}
    out["connects_cost"] = connects_cost(j)
    return out


def save(name: str, obj: dict) -> Path:
    obj = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), **obj}
    p = RESULTS / f"{name}.json"
    p.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    return p


def pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(math.ceil(q * len(s))) - 1)], 3)


def f1(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0}
