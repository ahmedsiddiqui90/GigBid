# Signature extension: X2 Proposal experiments (A/B test)

**What:** every job that reaches the writer is assigned, by a seeded hash of the job id, to one of two proposal
strategies defined in `agent/config.yaml` (`experiments.ab_test.arms`):

- `evidence_first`: open with the most relevant past result, then the plan.
- `question_first`: open with a sharp question about the client's problem, then the evidence.

The arm is stored with the proposal (`analysis.strategy`, proposal `meta.strategy` in GigSim), shown in the proposal
studio, and reported in Analytics (submitted vs replied per arm).

**How it is measured:** `python -m evals.runners.ab_test` re-uses the dev-set proposals from the agent evaluation
runs, scores each with GigSim's simulated client, and runs a two-proportion z-test (and Fisher's exact test, since
samples are small) on reply rate. Results: `evals/results/ab_test.json`.

**Honest limits:** with tens of proposals per arm the test only detects large effects (power note in the results
file); the simulated client does not model curiosity, so a question-first opening is judged only through must-have
coverage and generic-opening penalties. On a real account the same machinery would need weeks of traffic.
