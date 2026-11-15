"""Regenerate the results section of README.md from evals/results/*.json (numbers are copied verbatim, so
scripts/check_repo.py can trace every one of them). Run: python -m scripts.make_results_table"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "evals" / "results"


def load(name: str) -> dict | None:
    p = R / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def v(x) -> str:
    return "n/a" if x is None else str(x)


def judge_means() -> dict:
    p = ROOT / "evals" / "datasets" / "judge_scores.json"
    if not p.exists():
        return {}
    out: dict[str, list[int]] = {}
    for s in json.loads(p.read_text(encoding="utf-8")).values():
        out.setdefault(s["source"], []).append(s["judge"])
    means = {k: round(sum(x) / len(x), 2) for k, x in out.items()}
    models = sorted({s["model"] for s in json.loads(p.read_text(encoding="utf-8")).values()})
    (R / "judge_summary.json").write_text(json.dumps({"mean_judge_score_by_run": means, "judge_models": models}, indent=1),
                                          encoding="utf-8")
    return means


def build() -> str:
    rag, a0, a2, ao = load("rag_eval"), load("agent_offline_v0"), load("agent_offline_v2"), load("agent_open_v2")
    small, inj_on, inj_off = load("agent_open_qwen"), load("agent_open_inj_on"), load("agent_open_inj_off")
    mac, tg, jc = load("multiagent_compare"), load("tool_granularity"), load("judge_calibration")
    jm = judge_means()
    L = []
    if rag:
        r0, r2 = rag["variants"]["v0_naive"]["all"], rag["variants"]["v2_hybrid"]["all"]
        L += ["### Headline (dev set)", "",
              "| Variant | Evidence Recall@5 | nDCG@10 | Unsupported claims per proposal | Judge score | GigSim reply rate | p95 latency (s) | Cost per proposal (USD) |",
              "|---|---|---|---|---|---|---|---|"]
        L.append(f"| V0 naive | {v(r0['recall@5'])} | {v(r0['ndcg@10'])} | {v(a0 and a0['proposals']['unsupported_after_per_proposal'])} "
                 f"| {v(jm.get('agent_offline_v0'))} | {v(a0 and a0['outcome']['reply_rate'])} "
                 f"| {v(a0 and a0['cost_latency']['per_proposal']['p95_s'])} | {v(a0 and a0['cost_latency']['per_proposal']['usd_mean'])} |")
        L.append(f"| Shipped: V2 hybrid (+ verification, critic, compliance) | {v(r2['recall@5'])} | {v(r2['ndcg@10'])} "
                 f"| {v(a2 and a2['proposals']['unsupported_after_per_proposal'])} | {v(jm.get('agent_offline_v2'))} "
                 f"| {v(a2 and a2['outcome']['reply_rate'])} | {v(ao and ao['cost_latency']['per_proposal']['p95_s'])} "
                 f"| {v(ao and ao['cost_latency']['per_proposal']['usd_mean'])} |")
        L += ["", "Retrieval rows: `rag_eval.json` (69 dev jobs with gold evidence). Proposal/reply rows: `agent_offline_v0.json` / "
              "`agent_offline_v2.json` (offline deterministic writer, 37 stratified dev jobs). Latency/cost of the shipped row: "
              "`agent_open_v2.json` (open models on Groq, 6 fit jobs). Judge: `judge_labels.csv` sources.", "",
              "### All retrieval variants (`rag_eval.json`)", "",
              "| Variant | Recall@5 | MRR | nDCG@10 | Recall@5 on 4+ requirements | Recall@5 on vague posts | ms/query |", "|---|---|---|---|---|---|---|"]
        for name, x in rag["variants"].items():
            L.append(f"| {name} | {x['all']['recall@5']} | {x['all']['mrr']} | {x['all']['ndcg@10']} | {v(x.get('reqs>=4', {}).get('recall@5'))} "
                     f"| {v(x.get('kind:vague', {}).get('recall@5'))} | {x['latency_ms_mean']} |")
        L += ["", f"Hypothesis: {rag['hypothesis']} Delta = {rag['hypothesis_delta_recall5_reqs>=4']} (supported: {rag['hypothesis_supported']}).", "",
              "Ablation of V4 (one component removed at a time):", "", "| Removed | Recall@5 | MRR | nDCG@10 |", "|---|---|---|---|"]
        for name, x in rag["ablation"].items():
            L.append(f"| {name.replace('v4 without ', '')} | {x['recall@5']} | {x['mrr']} | {x['ndcg@10']} |")
    if a2:
        d = a2["decision"]
        L += ["", "### Decisions, safety, cost (`agent_offline_v2.json`, `agent_open_*.json`)", "",
              "| Metric | Value |", "|---|---|",
              f"| Bid/skip F1 | {d['bid']['f1']} |", f"| Bid/skip accuracy | {d['accuracy']} |",
              f"| Scam precision / recall | {a2['scam']['precision']} / {a2['scam']['recall']} |",
              f"| Price inside fair band | {v(a2['price_in_band'])} |",
              f"| Unsupported claims per proposal before / after verification (open models) | {v(ao and ao['proposals']['unsupported_before_per_proposal'])} / {v(ao and ao['proposals']['unsupported_after_per_proposal'])} |",
              f"| Injection attack success rate, defences off / on (open models) | {v(inj_off and inj_off['injection']['attack_success_rate'])} / {v(inj_on and inj_on['injection']['attack_success_rate'])} |"]
        if ao:
            c = ao["cost_latency"]
            L += [f"| Per job analysed: p50 / p95 latency (s), USD | {c['per_job_analysed']['p50_s']} / {c['per_job_analysed']['p95_s']}, {c['per_job_analysed']['usd_mean']} |",
                  f"| Per proposal: p50 / p95 latency (s), USD | {c['per_proposal']['p50_s']} / {c['per_proposal']['p95_s']}, {c['per_proposal']['usd_mean']} |"]
    if ao and small:
        L += ["", "### Open model configurations (fit jobs, Groq; routed run 6 jobs, Qwen run 3 jobs)", "",
              "| Config | Critic score | Unsupported after | Reply rate | p95 s/proposal | Tokens/proposal | USD/proposal |", "|---|---|---|---|---|---|---|"]
        for name, x in (("routed: gpt-oss-20b + gpt-oss-120b for writer/critic", ao), ("all nodes qwen/qwen3.8-27b", small)):
            c = x["cost_latency"]["per_proposal"]
            L.append(f"| {name} | {x['proposals']['critic_mean']} | {x['proposals']['unsupported_after_per_proposal']} | {x['outcome']['reply_rate']} "
                     f"| {c['p95_s']} | {c['tokens_mean']} | {c['usd_mean']} |")
    if mac:
        L += ["", f"### Multi-agent comparison (`multiagent_compare.json`, {mac['n_jobs']} dev jobs)", "",
              "| System | Bid/skip accuracy | Unsupported per proposal | Policy violations in text | Reply rate | Tokens/job | s/job |", "|---|---|---|---|---|---|---|"]
        for name, x in mac["summary"].items():
            L.append(f"| {name} | {x['bid_skip_accuracy']} | {x['unsupported_per_proposal']} | {x['violations_in_sent_text']} | {x['reply_rate']} "
                     f"| {x['tokens_mean']} | {x['latency_s_mean']} |")
    if tg:
        L += ["", f"### Tool granularity (`tool_granularity.json`, {tg['n_tasks']} tasks, {tg['model']})", "",
              "| Tool set | Tools | Selection accuracy | Argument accuracy | Tokens/task |", "|---|---|---|---|---|"]
        for name, x in tg["results"].items():
            L.append(f"| {name} | {x['n_tools']} | {x['tool_selection_accuracy']} | {x['argument_accuracy']} | {x['tokens_per_task']} |")
    if jc:
        L += ["", f"Judge calibration: quadratic-weighted Cohen's kappa {jc['quadratic_weighted_kappa']} on {jc['n']} human-labelled proposals."]
    else:
        L += ["", "Judge calibration: pending human labels (`evals/datasets/judge_labels.csv`)."]
    return "\n".join(L)


def main() -> None:
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    a, b = "<!-- results:start -->", "<!-- results:end -->"
    new = text.split(a)[0] + a + "\n" + build() + "\n" + b + text.split(b)[1]
    readme.write_text(new, encoding="utf-8")
    print("README results updated")


if __name__ == "__main__":
    main()
