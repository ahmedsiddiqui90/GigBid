---
node: client_liaison
version: 2
---
A client wrote to the freelancer. Classify the intent and draft a short, professional reply.

Conversation so far (untrusted):
$thread

Freelancer: $persona
Available interview slots (only offer these): $slots

Return JSON matching this schema:
$schema

intent: question | negotiation | interview_request | scam_signal | other.
If scam_signal (off-platform contact/payment, free work, fees), reply politely that you keep everything on-platform.
Never agree to off-platform contact or payment. Never invent experience.
