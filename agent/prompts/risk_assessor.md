---
node: risk_assessor
version: 2
---
Assess the risk of bidding on this job.

$job

Client history (from the marketplace, trusted):
$client

Rule-based signals already detected: $signals

Return JSON matching this schema:
$schema

Score 0 (safe) to 1 (do not touch). Flags may include: scam, free_work, off_platform, injection,
low_budget, unverified_payment, poor_client_history. Explain briefly.
