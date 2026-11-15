"""Collect failed dev jobs from evals/results/agent_*.json and group them into the report taxonomy:
missed evidence, wrong skip, wrong bid, mispriced, unsupported claim, generic opening, compliance miss, injection,
tool error. Writes evals/results/failure_analysis.json (the report discusses fixes per category)."""
from __future__ import annotations

import json
from collections import defaultdict

from evals.runners.common import RESULTS, dev_labels, gigsim_clients, gigsim_jobs, save


def main() -> None:
    labels = {x["job_id"]: x for x in dev_labels()}
    jobs, clients = gigsim_jobs(), gigsim_clients()
    cases: dict[str, list[dict]] = defaultdict(list)
    for p in sorted(RESULTS.glob("agent_*.json")):
        if p.stem.startswith("agent_test"):
            continue  # held-out split is reported separately
        r = json.loads(p.read_text(encoding="utf-8"))
        if "inj_off" in p.stem:  # defences disabled: record what got through, nothing else
            for i in r.get("injection", {}).get("cases", []):
                if i["attack_succeeded"]:
                    cases["injection (defences off)"].append({"run": p.stem, **i})
            continue
        for x in r.get("proposals_detail", []):
            if x["unsupported_before"]:
                cases["unsupported claim (caught by verifier)"].append({"run": p.stem, "job_id": x["job_id"],
                                                                        "n": x["unsupported_before"]})
            if x["revisions"] >= 2 and (x["critic"] or 0) < 0.7:
                cases["weak draft (critic limit reached)"].append({"run": p.stem, "job_id": x["job_id"], "critic": x["critic"]})
        for f in r.get("decision_failures", []):
            kind = "wrong skip" if f["gold"] == "bid" else "wrong bid"
            cases[kind].append({"run": p.stem, **f})
        for x in r.get("proposals_detail", []):
            lab = labels[x["job_id"]]
            job = jobs[x["job_id"]]
            h = clients[job["client_id"]]["hidden"]
            text = x["text"].lower()
            if x["unsupported_after"]:
                cases["unsupported claim"].append({"run": p.stem, "job_id": x["job_id"], "n": x["unsupported_after"]})
            if not x["replied"]:
                missing = [m for m in h["must_haves"] if m.lower() not in text]
                if missing:
                    cases["missed evidence / must-have not mentioned"].append({"run": p.stem, "job_id": x["job_id"],
                                                                               "missing": missing, "sim_score": x["sim_score"]})
                elif x["words"] < 80:
                    cases["too short after verification"].append({"run": p.stem, "job_id": x["job_id"], "words": x["words"]})
                else:
                    cases["generic or weak opening"].append({"run": p.stem, "job_id": x["job_id"], "sim_score": x["sim_score"]})
            del lab
        for i in r.get("injection", {}).get("cases", []):
            if i["attack_succeeded"]:
                cases["injection"].append({"run": p.stem, **i})
        price_fail = r.get("price_in_band")
        if price_fail is not None and price_fail < 1:
            cases["mispriced"].append({"run": p.stem, "price_in_band": price_fail})
    mc = RESULTS / "multiagent_compare.json"
    if mc.exists():
        for row in json.loads(mc.read_text(encoding="utf-8"))["rows"]:
            for sysname in ("react_single", "supervisor"):
                if "error" in row[sysname]:
                    cases["tool / model error (baselines)"].append({"job_id": row["job_id"], "system": sysname,
                                                                    "error": row[sysname]["error"][:80]})
    summary = {k: len(v) for k, v in cases.items()}
    save("failure_analysis", {"counts": summary, "cases": {k: v[:12] for k, v in cases.items()}})
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
