"""Assemble docs/report/REPORT.md + section files + numbers from evals/results into docs/report/GigBid_RD_Report.pdf.
Run: python -m scripts.build_report   (needs pandoc + a LaTeX engine)"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REP = ROOT / "docs" / "report"
RES = ROOT / "evals" / "results"


def j(name: str) -> dict | None:
    p = RES / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def multiagent() -> str:
    m = j("multiagent_compare")
    if not m:
        return "_Not run._"
    rows = ["| System | Jobs ok | Bid/skip accuracy | Unsupported per proposal | Policy violations in text | Reply rate | Tokens/job | s/job |",
            "|---|---|---|---|---|---|---|---|"]
    for k, x in m["summary"].items():
        rows.append(f"| {k} | {x['n']} | {x['bid_skip_accuracy']} | {x['unsupported_per_proposal']} | {x['violations_in_sent_text']} "
                    f"| {x['reply_rate']} | {x['tokens_mean']} | {x['latency_s_mean']} |")
    notes = REP / "multiagent_notes.md"
    return (f"All three systems use the same open model ({m['model_for_baselines']}) on {m['n_jobs']} dev jobs "
            f"(fit, scam, injection, low budget) [`multiagent_compare.json`]. The sample is small because of the free "
            f"tier's tokens-per-minute and per-day limits; treat differences as indicative.\n\n" + "\n".join(rows) + "\n\n"
            + (notes.read_text(encoding="utf-8") if notes.exists() else ""))


def ab() -> str:
    a = j("ab_test")
    if not a:
        return "_Not run._"
    arms = " vs ".join(f"{k} {v['replied']}/{v['n']} ({v['reply_rate']})" for k, v in a["arms"].items())
    return (f"Reply rate {arms}; difference {a['difference']}, z = {a['z']}, p = {a['p_value_z']} (z-test), "
            f"p = {a['p_value_fisher']} (Fisher). Not significant at 0.05; with these sample sizes the minimum detectable "
            f"difference at 80% power is {a['min_detectable_difference_80pct_power']}, so the test can only rule out large "
            f"effects [`ab_test.json`]. The arm is visible per proposal in the studio and per arm in Analytics.")


def hidden() -> str:
    h = j("agent_test_offline")
    if not h:
        return "_Not run._"
    c = h["cost_latency"]
    return (f"Held-out split (never used for tuning; generated with a different seed; {h['n_jobs']} jobs, deterministic profile) "
            f"[`agent_test_offline.json`]: bid/skip F1 {h['decision']['bid']['f1']}, scam precision/recall "
            f"{h['scam']['precision']}/{h['scam']['recall']}, price in band {h['price_in_band']}, unsupported claims after "
            f"verification {h['proposals']['unsupported_after_per_proposal']}, simulated reply rate {h['outcome']['reply_rate']}, "
            f"injection attack success {h['injection']['attack_success_rate']}; p95 {c['per_job_analysed']['p95_s']} s per job "
            f"analysed and {c['per_proposal']['p95_s']} s per proposal.\n\n"
            + (REP / "budgets.md").read_text(encoding="utf-8"))


def judge() -> str:
    c = j("judge_calibration")
    if not c:
        return "Human labels were not complete at submission time, so no kappa is reported and no judge score is used as evidence."
    return (f"Quadratic-weighted Cohen's kappa between the judge and my labels: {c['quadratic_weighted_kappa']} on {c['n']} "
            f"proposals (exact agreement {c['exact_agreement']}) [`judge_calibration.json`].")


def models() -> str:
    a, q = j("agent_open_v2"), j("agent_open_qwen")
    if not (a and q):
        return "_Not run._"
    def row(n, x):
        c = x["cost_latency"]["per_proposal"]
        return (f"| {n} | {x['n_proposals']} | {x['proposals']['critic_mean']} | {x['proposals']['unsupported_before_per_proposal']} "
                f"| {x['outcome']['reply_rate']} | {c['p95_s']} | {c['tokens_mean']} | {c['usd_mean']} |")
    nl = chr(10)
    head = ("| Config | Proposals | Critic score | Unsupported before verification | Reply rate | p95 s | Tokens | USD |"
            + nl + "|---|---|---|---|---|---|---|---|")
    return ("Two open configurations on dev fit jobs [`agent_open_v2.json`, `agent_open_qwen.json`]:" + nl + nl + head + nl
            + row("routed gpt-oss-20b / gpt-oss-120b (writer, critic)", a) + nl + row("all nodes qwen/qwen3.8-27b", q)
            + nl + nl + "The routed gpt-oss configuration ships: it is cheaper per token and both run on hardware we do not "
            "own; on this free tier the deciding factor is the separate daily quota, so Qwen is kept as the fallback model.")


def main() -> None:
    body = (REP / "REPORT.md").read_text(encoding="utf-8").replace("<!-- RESULTS-SECTIONS -->",
                                                                    (REP / "rd_ab.md").read_text(encoding="utf-8") + "\n\n"
                                                                    + (REP / "rd_c_rest.md").read_text(encoding="utf-8"))
    change = (ROOT / "docs" / "rd" / "change_request.md").read_text(encoding="utf-8").split("\n", 2)[2]
    body = (body.replace("<!-- MULTIAGENT -->", multiagent()).replace("<!-- CHANGE -->", change)
            .replace("<!-- AB -->", ab()).replace("<!-- FAILURES -->", (REP / "failures.md").read_text(encoding="utf-8").split("\n", 2)[2])
            .replace("<!-- SAFETY -->", (REP / "safety.md").read_text(encoding="utf-8")).replace("<!-- HIDDEN -->", hidden())
            .replace("<!-- JUDGE -->", judge()).replace("<!-- MODELS -->", models()))
    out_md = REP / "GigBid_RD_Report.md"
    out_md.write_text(body, encoding="utf-8")
    subprocess.run(["pandoc", str(out_md), "-o", str(REP / "GigBid_RD_Report.pdf"), "--pdf-engine=xelatex",
                    "-V", "mainfont=Segoe UI", "-V", "monofont=Consolas", "--toc", "-V", "colorlinks=true"], check=True)
    print("wrote", REP / "GigBid_RD_Report.pdf")


if __name__ == "__main__":
    main()
