"""R&D question A: does tool granularity change agent behaviour?

40 tasks with a known correct call, three tool sets offered to the same open model (single turn, tool choice auto):
  fine    - many narrow tools (17)
  coarse  - two multiplexed tools with an `action` enum
  ours    - the shipped MCP tool set with rewritten, specific descriptions
Metrics: tool-selection accuracy, argument accuracy (key argument correct), tokens per task.
Hypothesis: our set beats both; coarse tools lose argument accuracy, fine tools lose selection accuracy.
Usage: python -m evals.runners.tool_granularity [--model openai/gpt-oss-20b]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import time

from evals.runners.common import save


def fn(name, desc, props, req=None):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": req if req is not None else list(props)}}}


S = {"type": "string"}
FINE = [
    fn("get_job_description", "Get a job's description.", {"job_id": S}), fn("get_job_budget", "Get a job's budget.", {"job_id": S}),
    fn("get_job_skills", "Get a job's skills.", {"job_id": S}), fn("get_job_title", "Get a job's title.", {"job_id": S}),
    fn("get_client_rating", "Client rating.", {"client_id": S}), fn("get_client_spend", "Client spend.", {"client_id": S}),
    fn("get_client_payment_status", "Client payment verification.", {"client_id": S}),
    fn("get_hourly_rate_stats", "Hourly rate statistics.", {"category": S}), fn("get_fixed_budget_stats", "Fixed budget statistics.", {"category": S}),
    fn("search_case_studies", "Search case studies.", {"query": S}), fn("search_reviews", "Search reviews.", {"query": S}),
    fn("search_code", "Search code.", {"query": S}), fn("search_jobs_by_keyword", "Search jobs by keyword.", {"keyword": S}),
    fn("search_jobs_by_category", "Search jobs by category.", {"category": S}), fn("get_connects_balance", "Connects balance.", {"freelancer_id": S}),
    fn("get_case_study", "Get a portfolio item.", {"id": S}), fn("list_skills", "List skills.", {}, []),
]
COARSE = [
    fn("marketplace", "Marketplace operations.", {"action": {"type": "string", "enum": ["search_jobs", "get_job", "client_history", "market_stats", "connects"]},
                                                  "args": {"type": "object", "description": "arguments for the action"}}),
    fn("portfolio", "Portfolio operations.", {"action": {"type": "string", "enum": ["search", "get_item", "list_skills"]},
                                              "args": {"type": "object"}}),
]
OURS = [
    fn("search_jobs", "Search open freelance jobs by keywords (title, description, skills). Use for finding NEW jobs.", {"query": S, "category": S}, ["query"]),
    fn("get_job", "Full job post by job_id: title, description, skills, budget, screening questions, client_id, Connects cost.", {"job_id": S}),
    fn("get_client_history", "A client's marketplace history by client_id: payment verified, hires, total spend, rating, reviews. Use to judge client trust/risk.", {"client_id": S}),
    fn("get_market_stats", "Typical pay for a job category (ai_ml, web_dev, data_analysis, other): hourly and fixed-budget quartiles from real postings.", {"category": S}),
    fn("get_connects_balance", "The freelancer's current Connects balance by freelancer_id.", {"freelancer_id": S}),
    fn("search_evidence", "Search MY portfolio (case studies, READMEs, code, reviews, past proposals) for evidence proving a requirement or skill.", {"requirement": S}),
    fn("get_case_study", "Full text of one portfolio item by its id (e.g. cs-ai_ml-churn).", {"id": S}),
    fn("list_skills", "All skills my portfolio proves, with counts.", {}, []),
]


def tasks() -> list[dict]:
    rnd = random.Random(1)
    skills = ["XGBoost", "Stripe webhooks", "dbt models", "LangGraph agents", "Power BI dashboards", "React Native", "Airflow", "Whisper"]
    kws = ["churn model", "Next.js dashboard", "Tableau", "RAG chatbot", "Shopify theme", "ETL pipeline"]
    cats = ["ai_ml", "web_dev", "data_analysis"]
    out = []
    for i in range(5):
        j, c = f"dev-ai_ml-{rnd.randint(1, 40):03d}", f"cl-dev-fullstack-{rnd.randint(1, 40):03d}"
        out += [
            {"q": f"Show me the full post for job {j}.", "ours": ("get_job", "job_id", j), "fine": ({"get_job_description", "get_job_title"}, "job_id", j),
             "coarse": ("marketplace", "get_job", j)},
            {"q": f"Can I trust client {c}? Check their history.", "ours": ("get_client_history", "client_id", c),
             "fine": ({"get_client_rating", "get_client_payment_status", "get_client_spend"}, "client_id", c), "coarse": ("marketplace", "client_history", c)},
            {"q": f"What do {cats[i % 3]} jobs usually pay?", "ours": ("get_market_stats", "category", cats[i % 3]),
             "fine": ({"get_hourly_rate_stats", "get_fixed_budget_stats"}, "category", cats[i % 3]), "coarse": ("marketplace", "market_stats", cats[i % 3])},
            {"q": f"Find proof in my portfolio that I know {skills[i]}.", "ours": ("search_evidence", "requirement", skills[i].split()[0]),
             "fine": ({"search_case_studies", "search_code", "search_reviews"}, "query", skills[i].split()[0]), "coarse": ("portfolio", "search", skills[i].split()[0])},
            {"q": f"Look for new {kws[i]} jobs.", "ours": ("search_jobs", "query", kws[i].split()[0]),
             "fine": ({"search_jobs_by_keyword"}, "keyword", kws[i].split()[0]), "coarse": ("marketplace", "search_jobs", kws[i].split()[0])},
            {"q": f"How many Connects do I have left? My freelancer id is fl-{i}.", "ours": ("get_connects_balance", "freelancer_id", f"fl-{i}"),
             "fine": ({"get_connects_balance"}, "freelancer_id", f"fl-{i}"), "coarse": ("marketplace", "connects", f"fl-{i}")},
            {"q": f"Open my case study cs-ai_ml-{['churn', 'fraud', 'agent', 'mlops', 'speech'][i]}.", "ours": ("get_case_study", "id", "cs-ai_ml-"),
             "fine": ({"get_case_study"}, "id", "cs-ai_ml-"), "coarse": ("portfolio", "get_item", "cs-ai_ml-")},
            {"q": ["Which skills can my portfolio prove?", "List my skills.", "What am I good at according to my portfolio?",
                   "Summarise the skills I have evidence for.", "Give me my evidenced skill list."][i],
             "ours": ("list_skills", None, None), "fine": ({"list_skills"}, None, None), "coarse": ("portfolio", "list_skills", None)},
        ]
    return out


def check(kind: str, task: dict, call: dict | None) -> tuple[bool, bool]:
    if not call:
        return False, False
    name, args = call["name"], call.get("args") or {}
    exp = task[kind]
    if kind == "coarse":
        sel = name == exp[0] and args.get("action") == exp[1]
        inner = args.get("args") or {}
        val = exp[2]
        argok = sel and (val is None or any(val.lower() in str(v).lower() for v in inner.values()))
        return sel, argok
    names = exp[0] if isinstance(exp[0], set) else {exp[0]}
    sel = name in names
    argok = sel and (exp[1] is None or exp[2].lower() in str(args.get(exp[1], "")).lower())
    return sel, argok


async def main(a) -> None:
    from langchain_openai import ChatOpenAI

    from agent.settings import config

    prof = config().profiles["open"]
    llm = ChatOpenAI(model=a.model, base_url=prof["base_url"], api_key=os.environ.get(prof["api_key_env"]), temperature=0)
    sets = {"fine": FINE, "coarse": COARSE, "ours": OURS}
    ts = tasks()
    res = {}
    for kind, tools in sets.items():
        bound = llm.bind_tools(tools)
        sel = arg = tok = err = 0
        for t in ts:
            try:
                m = await bound.ainvoke([("system", "You are a freelancer assistant. Call exactly one tool to serve the request."),
                                         ("user", t["q"])])
                call = m.tool_calls[0] if m.tool_calls else None
                tok += (m.usage_metadata or {}).get("total_tokens", 0)
            except Exception:  # noqa: BLE001
                call, err = None, err + 1
                await asyncio.sleep(2)
            s, g = check(kind, t, call)
            sel += s
            arg += g
        n = len(ts)
        res[kind] = {"n_tools": len(tools), "tool_selection_accuracy": round(sel / n, 3), "argument_accuracy": round(arg / n, 3),
                     "tokens_per_task": round(tok / n, 1), "errors": err}
        print(kind, res[kind], flush=True)
        time.sleep(1)
    save("tool_granularity", {"model": a.model, "n_tasks": len(ts), "results": res,
                              "hypothesis": "our rewritten set beats fine (selection) and coarse (arguments)"})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="openai/gpt-oss-20b")
    args = ap.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main(args))
