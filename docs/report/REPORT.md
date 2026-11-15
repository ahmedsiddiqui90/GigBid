---
title: "GigBid: engineering design review"
subtitle: "AI-4016 Assignment II - multi-agent freelancer copilot"
author: "Ahmed Siddiqui | CS-C | 23K-0664"
date: "15 November 2026"
geometry: margin=2cm
fontsize: 10pt
---

Every number below is copied from a file in `evals/results/` (named in brackets); the README results section is
generated from the same files by `scripts/make_results_table.py`. Dev set only; tuning never touched the held-out split.

# 1. Problem and constraints

A freelancer loses hours scanning feeds, spends paid Connects on jobs they cannot win, sends generic proposals and
meets scams asking for free work or off-platform payment. GigBid automates discovery, assessment and drafting; the
freelancer keeps every decision. **Never automated:** submitting a proposal, sending a message, spending Connects,
claiming experience the portfolio does not show, contacting anyone off-platform. These are enforced in code
(`interrupt()` before every write; no code path submits without an approval; Compliance Guard; claim verification).

Budgets declared in `agent/config.yaml`: p95 latency 20 s per job analysed and 60 s per proposal; cost USD 0.002 per
job analysed and USD 0.01 per proposal, on open-weight models only.

**Starting point.** The starter kit contained no simulator, persona corpora or dev labels, so we built GigSim (our
own marketplace simulator with deterministic simulated clients), three synthetic personas and a 111-job labelled dev
set, and combined them with 112,660 real Upwork postings from two Kaggle datasets (pricing statistics and a real job
stream) - see `docs/DATA_CARD.md`. This matters for every result: the simulated client is a scoring function we wrote,
so "reply rate" measures agreement with that function.

# 2. Architecture

Two hand-written LangGraph graphs (`agent/graphs/`). The **bid graph** fans out Job Analyst, Risk Assessor and Fit
Matcher with `Send`, joins at a deterministic decision node, then Pricing, Writer, claim verification, a Critic loop
(max 2 revisions), Compliance Guard and an `interrupt()` approval before an idempotent submit. The **conversation
graph** classifies client intent, drafts a reply or interview slots (Workspace MCP), passes Compliance and waits for
approval. Both use a Postgres checkpointer; long-term memory is a LangGraph Postgres store with two namespaces (style
rules promoted after a pattern appears in 2 edits; outcome counts per category from marketplace events only).

All external capability is MCP: our Portfolio (evidence search, resources, prompts), Marketplace (read + write tools
with Pydantic schemas, annotations, idempotency keys, `dry_run`, bearer auth, per-user rate limit, append-only audit
log) and Workspace servers, plus the official Upwork MCP server and GitHub MCP. One marketplace port with two adapters
(`gigsim`, `upwork_live`) is selected by config. Each agent sees only allow-listed tools.

**Why each agent exists:** risk, fit, decision and compliance are deterministic code driven by configuration (auditable,
reproducible in CI, immune to text inside the job post); models write (Writer, Critic, Liaison), extract (Analyst) and
explain (Risk). Figures and the per-agent table: `docs/ARCHITECTURE.md`.

<!-- RESULTS-SECTIONS -->
