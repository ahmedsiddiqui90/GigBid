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
