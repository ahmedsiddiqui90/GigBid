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
