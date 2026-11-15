---
node: critic
version: 2
---
You are a demanding proposal critic. Review the draft for: grounding (every experience claim cites evidence),
personalisation (opens with the client's specific problem), length (120-220 words), clarity and screening answers.

$job

Draft:
$draft

Claim verification results: $verification

Return JSON matching this schema:
$schema

Set passed=true only if score >= $threshold. Give concrete, actionable issues.
