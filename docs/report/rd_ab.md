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
model family from the writer. <!-- JUDGE -->

**Open model choice.** <!-- MODELS -->
