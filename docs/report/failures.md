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
