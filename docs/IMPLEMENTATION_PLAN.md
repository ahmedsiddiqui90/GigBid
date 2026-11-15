# GigBid — Implementation Plan (lean, time-boxed)

Spec: [Assignment-II_AI-4016-GigBid.pdf](Assignment-II_AI-4016-GigBid.pdf). Deadline (extended):
**15 Nov 2026, 11:59 PM PKT** — a few hours. Rules for working: see [`CLAUDE.md`](../CLAUDE.md).

## What changed from the first plan

- **No GigSim was shipped.** The starter kit has only tiny sample data and placeholders. We build our
  own small simulator (`gigsim/`): jobs, clients with hidden preferences, Connects, proposals,
  messages, rate limit, random 5xx, and a deterministic simulated-client reply/hire model.
- **Data** = real Kaggle Upwork job postings (job stream realism + pricing statistics) + generated
  synthetic personas/portfolios/client histories/proposals/conversations/scam and injection jobs,
  each flagged `synthetic: true`. Documented in `docs/DATA_CARD.md`.
- **Scope cut to minimal honest versions.** Everything below is the smallest thing that satisfies
  the requirement; gaps are written down rather than over-built.

## Stack (simplest that meets the spec)

| Concern | Choice |
|---|---|
| Python | 3.12 venv, pip, `pyproject.toml` |
| Agents | LangGraph `StateGraph` (hand-written), `Send` for parallel branches, `interrupt()` approvals |
| Persistence | Postgres: LangGraph `PostgresSaver` checkpointer + `PostgresStore` memory + app tables |
| MCP | Official MCP Python SDK (FastMCP, streamable HTTP) + `langchain-mcp-adapters` |
| Retrieval | `fastembed` (BGE-small, CPU, ONNX) + numpy vector index, `bm25s`, fastembed cross-encoder reranker |
| LLMs | `open` profile: open-weight models on Groq (OpenAI-compatible). `offline` profile: deterministic heuristics (tests, CI, no key) |
| API | FastAPI + SSE |
| Worker | Arq on Redis (scheduled scouting, graph runs) |
| Web | Vite + React + TypeScript, client generated from OpenAPI (`openapi-typescript` + `openapi-fetch`) |
| Tests | pytest, in-memory MCP client tests, schema snapshot, Playwright (5 e2e) |
| Tracing | LangSmith if key present; always a local execution trace with one `trace_id` per run |
| Deploy | `infra/docker-compose.yml`; public host needs the owner (manual step) |
| Extension | X2 Proposal experiments (A/B in GigSim + significance test) |

## Task groups (one commit each)

| # | Group | Atomic tasks | Done when |
|---|---|---|---|
| 1 | **Scaffold** | git init; dir tree per spec; `pyproject.toml`; `Makefile`; `.env.example`; `.gitignore`; `agent/config.yaml` + `agent/policy.yaml`; settings loader; prompt loader | `pip install -e .` works |
| 2 | **Data** | Kaggle download script (kagglehub) + cleaning to `data/processed/jobs_real.parquet`; pricing stats by category; synthetic generator: 3 personas (CV, ~15 case studies, READMEs, reviews, ~60 past proposals w/ outcomes), clients with hidden prefs, job stream (real-derived + synthetic scams/dups/injections), dev set (~60 jobs/persona with gold bid/skip, scam, evidence ids, price band); `DATA_CARD.md` | `make seed` produces all files |
| 3 | **GigSim** | FastAPI sim: jobs, clients, Connects, proposals (idempotency), messages, events, rate limit, 5xx injection, simulated client reply/hire model, policy-update hook | sim serves on :8081, tests pass |
| 4 | **MCP servers** | Marketplace port + GigSim adapter + Upwork live adapter (OAuth skeleton, mapped tools); marketplace MCP (read/write tools, schemas, annotations, idempotency, dry_run, bearer auth, rate limiter, audit log); portfolio MCP (tools, resources, prompts, standalone CLI); workspace MCP (mock calendar/email); per-agent allowlists; `TOOLS.md`; in-memory tests + schema snapshot | tests pass; single-agent demo drafts a grounded proposal |
| 5 | **RAG** | Ingest + chunk + metadata; variants V0, V1 (decompose), V2 (hybrid RRF), V3 (rerank), V4 (outcome-aware), V8 (corrective loop); retriever factory; claim verification (split → support check → remove/rewrite) | `rag_eval` runs on dev set |
| 6 | **Agents & graphs** | Hand-offs (Pydantic); state + reducers; 9 nodes; bid graph (parallel `Send`, decide, pricing, writer, verifier, critic ≤2, compliance, `interrupt`, submit with idempotency); conversation graph; budgets → needs-attention; retries/fallback/dead-letter; style + outcome memory with promotion rules | integration test runs graph against GigSim, crash-resume test passes |
| 7 | **API & worker** | Auth (sessions, multi-user), onboarding, jobs, proposals/approvals (resume interrupt), messages, pipeline, runs + SSE, analytics, settings/memory; Arq worker with schedules + idempotent jobs; trace-id propagation; PII masking; encrypted tokens | API serves; worker scouts and analyses |
| 8 | **Web UI** | Generated TS client; screens: sign-in/onboarding, inbox, job detail, proposal studio (evidence hover, approve/edit/reject, dry-run), pipeline, messages, run viewer (SSE), analytics, settings (memory viewer); degraded banner; mobile CSS; 5 Playwright tests | e2e tests pass |
| 9 | **Evals & R&D** | rag_eval (Recall@5, MRR, nDCG@10), decision_eval (F1, scam P/R, price-in-band), gigsim_outcomes (reply/hire), judge + calibration sheet, cost/latency, ablation, tool-granularity study (40 tasks), multi-agent comparison (ReAct vs supervisor vs graph), injection ASR, A/B extension; results table script | `make eval` writes `evals/results/*.json` |
| 10 | **Ops** | Dockerfiles + compose; CI (lint, unit, contract, gigsim checksum, prompts-in-folder, secrets) + eval workflow with thresholds; RUNBOOK | CI config valid |
| 11 | **Change request + docs** | Apply policy update via config; README (results tables, trace links), ARCHITECTURE, ADRs, EXTENSION, AI_USAGE, report draft (markdown → PDF), failure taxonomy | docs complete |

## Manual steps for the owner (only what Claude cannot do)

Collected and requested as they become needed:

1. **Groq API key** (free) for the `open` model profile → `GROQ_API_KEY` in `.env`.
2. **LangSmith API key** (optional, free) for public trace links → `LANGSMITH_API_KEY`.
3. **GitHub repo** (public) creation and push.
4. **Public deployment** (host account) + reviewer login in the Classroom private comment.
5. **Human labels**: 30 proposals for judge calibration; classmates' blind pairwise ratings (optional).
6. **Publish** the Portfolio MCP server (PyPI/uvx), technical write-up, 3-minute demo video, Classroom submission.
7. **Change request text** (2 Nov policy update) if available; otherwise we simulate one and say so.
