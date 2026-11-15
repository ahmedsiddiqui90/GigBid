---
node: proposal_writer
version: 3
---
Write a proposal for this job as the freelancer below. Strategy: $strategy

$job

Freelancer: $persona
Price to propose: $price

Evidence you may cite (ONLY these; each has an id):
$evidence

Style rules learned from the freelancer's own edits (follow them):
$style_rules

Critic feedback from the previous attempt (fix every point, if any):
$critique

Return JSON matching this schema:
$schema

Rules:
- 120-220 words. First sentence must be specific to this client's problem, never "Dear Sir" or "I am writing".
- Every sentence that claims experience must end with the evidence id in square brackets, e.g. [ev-ai-003].
- Only claim what the evidence states. No emails, links, phone numbers, guarantees.
- Answer each screening question in 1-3 sentences, citing evidence ids the same way.
