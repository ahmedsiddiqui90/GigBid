---
node: job_analyst
version: 2
---
Extract a structured JobSpec from the job post below.

$job

Return JSON matching this schema:
$schema

Guidance:
- requirements: 3-7 short, specific, independently checkable requirements (skills, deliverables, domain).
- hidden_needs: what the client probably cares about but did not say (e.g. maintainability, speed).
- category: one of web_dev, ai_ml, data_analysis, mobile, design, writing, devops, other.
