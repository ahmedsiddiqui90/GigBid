"""R&D question C: is the multi-agent design worth it?

Compares on the same dev jobs:
  (a) one ReAct agent holding all tools (langgraph.prebuilt.create_react_agent)
  (b) a prebuilt supervisor (langgraph-supervisor) over research / analysis / writing workers
  (c) our hand-built bid graph
Metrics: bid/skip accuracy, unsupported claims per proposal, compliance violations caught (policy hits in the raw
proposal that our Compliance Guard would remove), GigSim simulated reply rate, tokens and latency.
Usage: python -m evals.runners.multiagent_compare --stride 9
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time

from evals.runners.common import dev_labels, gigsim_clients, gigsim_jobs, profile, public_job, save


def _parse_final(text: str) -> dict:
    m = re.findall(r"\{[^{}]*\"decision\"[^{}]*\}", text, re.S)
    if m:
        try:
            return json.loads(m[-1])
        except json.JSONDecodeError:
            pass
    dec = "skip" if re.search(r"\bskip\b", text, re.I) and not re.search(r"\bbid\b.*\bproposal\b", text, re.I) else "bid"
    return {"decision": dec, "proposal": text, "price": 0}


def _usage(msgs) -> int:
    return sum((getattr(m, "usage_metadata", None) or {}).get("total_tokens", 0) for m in msgs)


async def tools_all(uid: str):
    from langchain_mcp_adapters.client import MultiServerMCPClient

    from agent.mcp_client import _connections

    client = MultiServerMCPClient(_connections(uid, "compare"))
    tools = await client.get_tools()
    keep = {"get_job", "get_client_history", "get_market_stats", "search_evidence", "get_case_study", "list_skills"}
    return [t for t in tools if t.name in keep]


def job_prompt(job: dict, persona: str) -> str:
    from agent.prompts import load_prompt
    from agent.safety.untrusted import wrap

    p = profile(persona)
    return load_prompt("react_agent").render(persona=f"{p['name']} ({persona}), ${p['hourly_rate']}/h, floor ${p['floor_rate']}/h. "
                                            f"Use filters.persona='{persona}' in search_evidence.",
                                            job=wrap(f"job_id: {job['job_id']}\nclient_id: {job['client_id']}\n{job['title']}\n"
                                                     f"Budget: {job['budget']}\n{job['description']}"))


async def run_react(llm, tools, job, persona):
    from langgraph.prebuilt import create_react_agent

    agent = create_react_agent(llm, tools)
    t0 = time.perf_counter()
    out = await agent.ainvoke({"messages": [("user", job_prompt(job, persona))]}, {"recursion_limit": 16})
    return _parse_final(out["messages"][-1].content), _usage(out["messages"]), time.perf_counter() - t0


async def run_supervisor(llm, tools, job, persona):
    from langgraph.prebuilt import create_react_agent
    from langgraph_supervisor import create_supervisor

    by = {t.name: t for t in tools}
    research = create_react_agent(llm, [by["search_evidence"], by["get_case_study"]], name="researcher",
                                  prompt="Find portfolio evidence ids for each job requirement.")
    analyst = create_react_agent(llm, [by["get_client_history"], by["get_market_stats"]], name="analyst",
                                 prompt="Assess client risk and a fair price.")
    writer = create_react_agent(llm, [], name="writer", prompt="Write the final answer JSON as instructed.")
    sup = create_supervisor([research, analyst, writer], model=llm,
                            prompt="Coordinate the team to decide bid/skip and write a grounded proposal. "
                                   "End with the JSON object requested by the user.").compile()
    t0 = time.perf_counter()
    out = await sup.ainvoke({"messages": [("user", job_prompt(job, persona))]}, {"recursion_limit": 30})
    return _parse_final(out["messages"][-1].content), _usage(out["messages"]), time.perf_counter() - t0


def score_text(job, lab, text: str, price: float) -> dict:
    from agent.nodes.compliance import check_text
    from gigsim.app import client_decision
    from rag.index.store import load_index
    from rag.verify import heuristic_check, split_claims

    idx = load_index(lab["persona"])
    ev = {i: {"id": i, "snippet": idx.by_id[i]["text"], "skills": idx.by_id[i].get("skills", [])}
          for i in re.findall(r"\[([a-z]{2,4}-[\w-]+)\]", text) if i in idx.by_id}
    unsup = sum(heuristic_check(c, ev).label == "unsupported" for c in split_claims(text))
    _, verdict = check_text(text, {"injection_text": []}, None)
    violations = len(verdict.edits) + int(verdict.blocked)
    if lab.get("canary") and lab["canary"].lower() in text.lower():
        violations += 1
    sim = client_decision(job, gigsim_clients()[job["client_id"]], text, price or 0)
    return {"unsupported": unsup, "violations": violations, "replied": sim["replied"]}


async def main(a) -> None:
    import os

    os.environ.setdefault("MODEL_PROFILE", "open")
    from langchain_openai import ChatOpenAI
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    from agent.graphs.bid_graph import build_bid_graph
    from agent.settings import config
    from evals.runners.agent_eval import run_one

    prof = config().profiles["open"]
    llm = ChatOpenAI(model=a.model, base_url=prof["base_url"], api_key=os.environ.get(prof["api_key_env"]), temperature=0.2, max_retries=6)
    labels = dev_labels()[:: a.stride]
    jobs = gigsim_jobs()
    graph = build_bid_graph(InMemorySaver(), InMemoryStore())
    rows = []
    for lab in labels:
        job = public_job(jobs[lab["job_id"]])
        tools = await tools_all(f"cmp-{lab['persona']}")
        rec = {"job_id": lab["job_id"], "kind": lab["kind"], "gold": lab["decision"]}
        for name, fn in (("react_single", run_react), ("supervisor", run_supervisor)):
            try:
                out, tok, lat = await fn(llm, tools, job, lab["persona"])
                dec = str(out.get("decision", "skip")).lower()
                s = score_text(job, lab, str(out.get("proposal", "")), float(out.get("price") or 0)) if dec == "bid" else {}
                rec[name] = {"decision": dec, "tokens": tok, "latency_s": round(lat, 1), **s}
            except Exception as e:  # noqa: BLE001
                rec[name] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
        r = await run_one(graph, lab, job, None)
        st = r["state"]
        dec = "bid" if (st.get("decision") or {}).get("action") == "bid" and st.get("status") != "skipped" else "skip"
        tok = sum(u.get("tokens_in", 0) + u.get("tokens_out", 0) for u in st.get("usage", []))
        s = {}
        if dec == "bid" and st.get("draft"):
            s = score_text(job, lab, st["draft"]["cover_letter"], (st.get("price") or {}).get("amount", 0))
            s["violations_caught_by_guard"] = len((st.get("compliance") or {}).get("edits", []))
        rec["our_graph"] = {"decision": dec, "tokens": tok, "latency_s": round(r["latency_s"], 1), **s}
        rows.append(rec)
        await asyncio.sleep(a.cooldown)  # stay under the free-tier tokens-per-minute limit
        print(json.dumps(rec)[:400], flush=True)

    summary = {}
    for sysname in ("react_single", "supervisor", "our_graph"):
        ok = [r for r in rows if "error" not in r[sysname]]
        props = [r[sysname] for r in ok if r[sysname]["decision"] == "bid" and "replied" in r[sysname]]
        summary[sysname] = {
            "n": len(ok), "errors": len(rows) - len(ok),
            "bid_skip_accuracy": round(sum(r[sysname]["decision"] == r["gold"] for r in ok) / max(1, len(ok)), 3),
            "unsupported_per_proposal": round(sum(p["unsupported"] for p in props) / max(1, len(props)), 2),
            "violations_in_sent_text": sum(p["violations"] for p in props),
            "reply_rate": round(sum(p["replied"] for p in props) / max(1, len(props)), 3),
            "tokens_mean": round(sum(r[sysname]["tokens"] for r in ok) / max(1, len(ok))),
            "latency_s_mean": round(sum(r[sysname]["latency_s"] for r in ok) / max(1, len(ok)), 1),
        }
    p = save("multiagent_compare", {"model_for_baselines": a.model, "n_jobs": len(rows), "summary": summary, "rows": rows})
    print(p, json.dumps(summary, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=9)
    ap.add_argument("--model", default="openai/gpt-oss-20b")
    ap.add_argument("--cooldown", type=float, default=30)
    args = ap.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main(args))
