# Change request: platform policy update

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
