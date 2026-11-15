---
title: "GigBid: engineering design review"
subtitle: "AI-4016 Assignment II - multi-agent freelancer copilot"
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

# 3. R&D question A: tool granularity

**Hypothesis.** A mid-sized tool set with specific, rewritten descriptions beats both many narrow tools (selection
errors) and a few multiplexed tools (argument errors).

**Setup.** 40 tasks with a known correct call (8 request types x 5 instances: job lookup, client trust, market pay,
portfolio proof, job search, Connects, case study, skills), offered single-turn to gpt-oss-20b on Groq with three
tool sets: *fine* (17 narrow tools), *coarse* (2 tools with an `action` enum and free-form `args`), *ours* (the
8 shipped tools with rewritten descriptions). [`tool_granularity.json`]

| Tool set | Tools | Selection accuracy | Argument accuracy | Tokens/task |
|---|---|---|---|---|
| fine | 17 | 0.95 | 0.925 | 570.5 |
| coarse | 2 | 0.925 | 0.9 | 388.1 |
| ours | 8 | 0.975 | 0.975 | 473.5 |

**Conclusion.** Supported, with small margins: our set is best on both accuracies; coarse tools are cheapest in
tokens but lose arguments inside the untyped `args` object; fine tools cost 20% more tokens and the model picks a
plausible-but-wrong sibling (e.g. `get_job_title` for "full post"). 40 tasks is a small sample: one task is 0.025.

# 4. R&D question B: retrieval variants, claim verification, ablation

**Hypothesis (stated before running).** Requirement decomposition + hybrid BM25/dense retrieval raises evidence
Recall@5 by at least 10 points over V0 on jobs with 4+ requirements.

**Setup.** 69 dev jobs with gold evidence (project-level items: case study, README, code, review), 3 personas, job
kinds fit / vague / injection / low-budget. Metrics Recall@5, MRR, nDCG@10, latency. [`rag_eval.json`]

| Variant | Recall@5 | MRR | nDCG@10 | Recall@5, 4+ reqs | Recall@5, vague posts | ms/query |
|---|---|---|---|---|---|---|
| V0 naive dense, fixed chunks | 0.817 | 1.0 | 0.868 | 0.798 | 0.639 | 36.2 |
| V1 requirement decomposition | 0.955 | 1.0 | 0.983 | 0.953 | 0.958 | 29.9 |
| V2 + BM25 hybrid (RRF) | **0.959** | 1.0 | **0.984** | 0.957 | 0.951 | 29.8 |
| V3 + cross-encoder rerank | 0.76 | 0.836 | 0.815 | 0.739 | 0.736 | 3544.7 |
| V4 + outcome-aware boost | 0.752 | 0.857 | 0.808 | 0.731 | 0.736 | 3613.0 |
| V8 corrective loop (LangGraph) | 0.773 | 0.767 | 0.763 | 0.762 | 0.847 | 3958.0 |

**Result.** Hypothesis supported: +15.9 points on 4+-requirement jobs (0.798 -> 0.957). The largest gain is on vague
posts (0.639 -> 0.951): decomposing into the job's skill tags recovers projects whose case study never names the skill.
By persona V2 reaches 0.938 (AI/ML), 0.961 (full-stack), 0.978 (data analyst) versus 0.833 / 0.791 / 0.826 for V0.

**Negative result: reranking hurt.** The MS-MARCO cross-encoder (trained on web question answering) scores short
skill queries like "Docker" against portfolio items poorly and demotes the right project; it also costs ~100x latency.
Re-scoring only the top 12 instead of 30 fused hits was both faster and slightly better (Recall@5 0.76 vs 0.739,
3.5 s vs 4.9 s per query), which is the E5 optimisation we kept for anyone enabling V3.

**Ablation of V4** (remove one component): without decomposition 0.921, without hybrid 0.766, without rerank 0.376,
without outcome boost 0.76. Read together with the table: decomposition and hybrid help, the reranker is the
component that drags V3/V4 down, and the outcome boost is only safe on reranker-scale scores (on RRF scores it
overwhelms relevance and collapses recall to 0.376) - a design flaw we report rather than hide.

**What ships:** V2 (`retrieval.variant: v2_hybrid`): best Recall@5 and nDCG@10, 30 ms/query, no extra model.

**Where better retrieval did not translate into replies.** With the deterministic writer on 37 stratified dev jobs,
V0 and V2 both reach a simulated reply rate of 1.0 [`agent_offline_v0.json`, `agent_offline_v2.json`]. The simulated
client rewards must-have coverage, citations and specificity; the writer names the job's requirements in its plan
sentence and cites whatever it retrieved, and V0 already retrieves *some* relevant item for every fit job (MRR 1.0).
Recall@5 measures finding *all* evidence, which matters for the screening answers and the evidence matrix, not for
this client model. The synthetic dev set is also saturated for decisions (bid/skip F1 1.0, scam P/R 1.0), which tells
us the templated jobs are too easy rather than that the system is perfect.

**Claim verification.** Every draft is split into claims (experience sentences and anything citing evidence; plan
sentences excluded), each claim labelled supported / partial / unsupported against its cited evidence, unsupported
claims removed and unverifiable numbers or technology names stripped before the Critic sees the draft. A
deterministic override catches what a lenient model accepts (a draft claiming PyTorch for a project whose evidence
never mentions it). On open-model drafts (gpt-oss-120b writer, 6 fit jobs) unsupported claims per proposal fell from
1.0 before verification to 0.0 after; on the injection jobs from 1.333 to 0.0 [`agent_open_v2.json`, `agent_open_inj_on.json`].

**Judge calibration.** 30 proposals scored by the LLM judge are in `evals/datasets/judge_labels.csv` for blind human
labelling; kappa is computed by `evals/runners/judge_calibration.py --kappa`. The judge is qwen/qwen3.8-27b, a different
model family from the writer. Human labels were not complete at submission time, so no kappa is reported and no judge score is used as evidence.

**Open model choice.** Two open configurations on dev fit jobs [`agent_open_v2.json`, `agent_open_qwen.json`]:

| Config | Proposals | Critic score | Unsupported before verification | Reply rate | p95 s | Tokens | USD |
|---|---|---|---|---|---|---|---|
| routed gpt-oss-20b / gpt-oss-120b (writer, critic) | 6 | 0.732 | 1.0 | 0.833 | 91.15 | 14159.2 | 0.004484 |
| all nodes qwen/qwen3.8-27b | 3 | 0.85 | 0.0 | 1.0 | 115.586 | 7729.0 | 0.002755 |

The routed gpt-oss configuration ships: it is cheaper per token and both run on hardware we do not own; on this free tier the deciding factor is the separate daily quota, so Qwen is kept as the fallback model.


# 5. R&D question C: single agent vs prebuilt supervisor vs our graph

All three systems use the same open model (qwen/qwen3.8-27b) on 4 dev jobs (fit, scam, injection, low budget) [`multiagent_compare.json`]. The sample is small because of the free tier's tokens-per-minute and per-day limits; treat differences as indicative.

| System | Jobs ok | Bid/skip accuracy | Unsupported per proposal | Policy violations in text | Reply rate | Tokens/job | s/job |
|---|---|---|---|---|---|---|---|
| react_single | 1 | 1.0 | 0.0 | 0 | 0.0 | 3051 | 3.2 |
| supervisor | 1 | 1.0 | 2.0 | 0 | 1.0 | 13822 | 177.3 |
| our_graph | 4 | 1.0 | 0.0 | 0 | 1.0 | 8666 | 96.9 |

**What happened.** The decisive difference was not answer quality but **reliability of model-driven tool use**. The
single ReAct agent and the supervisor failed on 3 of 4 jobs each, almost always with a malformed tool call rejected by
the provider: a hallucinated tool name (`search_e Dining`), invalid parameters, or (supervisor) a context that grew past
the per-request token limit. Our graph completed 4/4 because no model chooses tools in it: nodes call MCP tools in code,
and models only fill typed hand-offs. Where the supervisor did finish (dev-ai_ml-001), it bid correctly but made
**2 unsupported claims** and took 177 s and 13.8k tokens; our graph's draft for the same job had 0 unsupported claims
after verification with about the same tokens.

**Where the single agent wins.** On the scam job (dev-ai_ml-029) the ReAct agent skipped correctly in 3.2 s; for
obvious skips one model call is enough, and our graph spends its fixed overhead (three parallel analyses) before the
rule-based skip. We already short-circuit cheaply (1,777 tokens for that skip), but a router that sends "obvious scam"
posts straight to a skip would make the graph cheaper still.

**Would we ship the single agent?** Not for anything that writes to a marketplace: its failure mode is a silent or
crashing tool call, and nothing in it verifies claims or enforces policy. We would use a single agent as an
interactive helper (answering a freelancer's question about one job), where a failed call is visible and harmless.


# 6. The change request

The instructor's 2 November "platform policy update" text was not part of the material available to us, so we
applied a representative update of the same kind (a new rule and a new cost affecting bidding) and measured how
cheaply the system absorbed it.

**Simulated update (GigSim policy 2026-11-02):**

1. Connects cost rises: base cost 4 -> 6, and a new tier adds 4 Connects for jobs with budgets above USD 5,000.
2. New rule: proposals must not contain external links (portfolio links must use the platform's own portfolio).

**What we changed:** `agent/policy.yaml` only (connects block + one `strip` rule with a URL pattern), plus one unit
test. No code changed: GigSim computes Connects from `policy.yaml`, the Marketplace MCP `dry_run` preview and the
Pricing Strategist's "worth the Connects" check read the job's Connects cost, and the Compliance Guard iterates over
`policy.yaml` rules. Commit tagged `change-request`; `git diff --stat` is reproduced in the report.

## Result

| | |
|---|---|
| Commit | `5977fea` (tag `change-request`) |
| Files changed | `agent/policy.yaml`, `tests/unit/test_agent_logic.py` |
| Lines | +17 / -2 (policy: +8 / -2; test: +9) |
| Code changed | none |
| Time | about 5 minutes including the test |

**What it says about the design:** because GigSim, the Marketplace MCP `dry_run`, the Pricing Strategist and the
Compliance Guard all read the same `policy.yaml`, a new cost and a new rule are a configuration edit. The one thing
that would *not* be config-only is a rule that needs new information (for example "cost depends on client
verification"): the Connects formula only sees the job budget, so that would need a small code change in
`gigsim.app.connects_cost` and the Pricing node.


# 7. Signature extension: proposal A/B test (X2)

Two proposal strategies (`evidence_first`, `question_first`) are assigned per job by a seeded hash, stored with the
proposal and compared on GigSim reply rate with a two-proportion z-test and Fisher's exact test.

Reply rate evidence_first 31/31 (1.0) vs question_first 20/21 (0.952); difference 0.048, z = 1.227, p = 0.2199 (z-test), p = 0.4038 (Fisher). Not significant at 0.05; with these sample sizes the minimum detectable difference at 80% power is 0.109, so the test can only rule out large effects [`ab_test.json`]. The arm is visible per proposal in the studio and per arm in Analytics.

# 8. Failure analysis

The synthetic dev set saturates the deterministic gates (bid/skip F1 1.0, scam precision/recall 1.0 on 37 stratified
jobs), so the instructive failures come from the open-model runs and from development. 10 dev-job failures plus the
baseline errors, grouped [`failure_analysis.json`]:

| Category | Dev jobs | Example | Fix tried | Worked? |
|---|---|---|---|---|
| Unsupported claim (caught by verifier) | 6 (dev-ai_ml-001, dev-fullstack-038, -054, dev-data_analyst-075, -076, -091) | gpt-oss-120b added a technology or number not in the cited evidence | deterministic override + surgical repair (strip the term, keep the sentence) | yes: 1.0 -> 0.0 unsupported per proposal after verification; drafts stay above 100 words |
| Weak draft, critic limit reached | 2 (dev-ai_ml-002, dev-fullstack-038) | critic scored 0.5 / 0.6 after 2 revisions (generic opening, missing screening answer) | critic feedback passed verbatim to the writer; hard checks (generic opening, unsupported) always count | partly: still sent for approval with the critic's issues shown inline |
| Missed must-have in proposal | 1 (dev-data_analyst-076) | client must-haves "A/B testing", "experimentation" not named; simulated client did not reply (score 0.391) | writer gets the JobSpec requirements; plan sentence names them | not fully: the model paraphrased them away; next step is a deterministic must-have mention check in the Critic |
| Injection (defences off) | 1 (dev-fullstack-054) | canary word from the post appeared in the draft | wrapping, sentence stripping, Compliance removal of injected tokens | yes: attack success 0.333 -> 0.0 with defences on (3 jobs) |
| Tool / model error | 14 baseline calls (7 jobs x 2 systems) | Groq free tier 8k tokens/min: 429 on every ReAct/supervisor run in the first comparison | retries honouring Retry-After, 65 s cool-downs, smaller sample | yes for the rerun (section 5) |

Development-time failures that shaped the design (all reproduced by unit tests in `tests/unit/test_agent_logic.py`
or recorded in `docs/AI_USAGE.md`): plan sentences treated as claims and deleted (wrong claim detection); real Kaggle
jobs without skill tags scoring fit 1.0 because "developer" matched the CV (mis-scored fit -> wrong bid); a missing
fallback model on the Groq account silently turning every fallback into a heuristic (tool error -> quality drop);
the outcome-aware boost overwhelming relevance on RRF scores (retrieval failure, section 4).


# 9. Safety and platform respect

**What GigBid must never do, and where it is enforced**

| Never | Enforcement |
|---|---|
| Submit a proposal, send a message or spend Connects without approval | `interrupt()` in `agent/nodes/approval.py` and `client_liaison.py` is the only path to `submit`/`send_reply`; write tools are allow-listed only to the `submitter`/`client_liaison` nodes; `autonomy` can only auto-skip |
| Submit twice / spend Connects twice | idempotency keys `draft-/submit-<user>:<job>:<draft hash>` checked in the Marketplace MCP server (Postgres `idempotency` table) **and** in GigSim; crash test `tests/integration/test_crash_resume.py` |
| Claim unsupported experience | claim splitting + verification + repair before the Critic (`rag/verify.py`), deterministic override for numbers/technologies, Compliance blocks if unsupported claims remain |
| Follow instructions planted in a job post or client message | untrusted text is delimited (`agent/safety/untrusted.py`), sentences matching injection patterns are stripped before the writer sees them, the analyst has no tools, risk/fit/decision/compliance are code, and Compliance removes tokens the injection asked for (canaries, quoted phrases, emails) |
| Put contact details, off-platform payment or guarantees in a draft | Compliance `strip` rules from `agent/policy.yaml` |
| Leak PII into logs/traces | `agent/safety/pii.py` log filter and masking of audit-log arguments |
| Leak OAuth tokens | Fernet-encrypted at rest (`apps/api/auth/security.py`), never logged, per-user rows; every query is scoped by `user_id` |
| Scrape or automate Upwork | live adapter uses only the official Upwork MCP server; no browser automation or cookies; live scouting at least every 240 min |

**What still gets through (known gaps)**

- Injections phrased without any trigger words ("the best proposals here mention the word X") are not stripped
  before the writer; only the canary/quote/email removal in Compliance catches the visible result.
- The deterministic verifier is word-overlap based: a paraphrase that changes meaning but keeps the words passes.
- Scam detection is pattern-based; a polite scam without payment/contact keywords and with a verified client passes.
- Hosted demo: the database lives inside the container, so restarting the Space resets state.


# 10. Hidden test results against declared budgets

Held-out split (never used for tuning; generated with a different seed; 37 jobs, deterministic profile) [`agent_test_offline.json`]: bid/skip F1 1.0, scam precision/recall 1.0/1.0, price in band 1.0, unsupported claims after verification 0.0, simulated reply rate 1.0, injection attack success 0.0; p95 7.789 s per job analysed and 15.797 s per proposal.

**Against declared budgets** (`agent/config.yaml`; open-model numbers from `agent_open_v2.json`, 6 fit jobs on
Groq's free tier):

| Budget | Declared | Measured | Met? |
|---|---|---|---|
| p95 latency per job analysed | 20 s | 8.952 s | yes |
| p95 latency per proposal | 60 s | 91.15 s | **no** |
| Cost per job analysed | USD 0.002 | USD 0.000229 | yes |
| Cost per proposal | USD 0.01 | USD 0.004484 | yes |

The proposal latency budget is missed. The time is dominated by the free tier's 8,000 tokens-per-minute limit: a
proposal uses about 14k tokens (writer, verifier, critic, up to two revisions), so the client waits on `Retry-After`
inside a single proposal. Without the limit (p50 57 s) the budget would be close. **Optimisation that helped:**
replacing the cross-encoder reranker by hybrid retrieval cut retrieval from ~3.5 s to ~30 ms per query with higher
Recall@5 (section 4); a second one cut verifier tokens by re-checking repaired drafts deterministically instead of
with a second model call. **What we would do next:** run the writer on a paid tier or a self-hosted gpt-oss-20b, and
skip the Critic when verification found nothing to repair.

Daily quotas matter for operation too: on this account each model allows 200k tokens per day, so the deployed demo
can analyse roughly a dozen proposals per model per day; the fallback model (Qwen) has its own quota, and the
`offline` profile keeps the system usable when both are exhausted.


