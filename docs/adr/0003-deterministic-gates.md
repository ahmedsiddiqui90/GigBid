# ADR 0003: deterministic risk, fit, decision and compliance

**Decision:** these nodes are rules driven by agent/config.yaml and agent/policy.yaml; LLMs only add explanations/flags.
**Why:** they must be auditable, reproducible in CI, cheap, and immune to prompt injection inside job posts.
**Trade-off:** less nuance on unusual jobs; documented in the failure analysis.
