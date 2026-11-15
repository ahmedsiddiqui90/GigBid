# MCP tools

Generated from the server registries (`python -m scripts.gen_tools_doc`). Agents never call GigSim, Upwork, the database or files directly: every capability is one of these tools, and each agent gets only the tools named in `agent/config.yaml` (`mcp.allowlists`).

| Tool | Server | R/W | Annotations | Auth | Description |
|---|---|---|---|---|---|
| `search_evidence` | portfolio | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False | bearer token (HTTP) / none (stdio) | Find portfolio evidence (case studies, READMEs, code, reviews, past proposals) proving a requirement. |
| `get_case_study` | portfolio | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False | bearer token (HTTP) / none (stdio) | Full text and metadata of one portfolio item (case study, README, review, proposal) by id. |
| `list_skills` | portfolio | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False | bearer token (HTTP) / none (stdio) | All skills evidenced in the portfolio, with how many items support each. |
| `search_jobs` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer token + per-user rate limit + audit log | Search open jobs by keywords (matches title, description, skills). Returns newest first. |
| `get_job` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer token + per-user rate limit + audit log | Full job post (title, description, skills, budget, screening questions, client_id, connects_cost). |
| `get_client_history` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer token + per-user rate limit + audit log | Client's marketplace history: payment verification, hires, total spend, rating, reviews. |
| `get_market_stats` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer token + per-user rate limit + audit log | Pricing statistics for a job category from real historical postings (hourly and fixed budget quartiles). |
| `get_connects_balance` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer token + per-user rate limit + audit log | Current Connects balance for the freelancer. |
| `list_messages` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer token + per-user rate limit + audit log | Client conversation threads for the freelancer, with all messages. |
| `list_events` | marketplace | read | readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer token + per-user rate limit + audit log | Pipeline events (viewed, replied, interview, hired, lost) after event id `since`. |
| `create_proposal_draft` | marketplace | write | readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True | bearer token + per-user rate limit + audit log | Create a proposal DRAFT on the marketplace (spends no Connects). Use dry_run=true for the approval preview. |
| `submit_proposal` | marketplace | write | readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True | bearer token + per-user rate limit + audit log | Submit an approved draft. SPENDS CONNECTS. Only call after explicit human approval. Idempotent by key. |
| `send_message` | marketplace | write | readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True | bearer token + per-user rate limit + audit log | Send an approved message to a client thread. Only call after explicit human approval. Idempotent by key. |
| `free_slots` | workspace | read | readOnlyHint=True, idempotentHint=True, openWorldHint=False | bearer token + audit log | Free interview slots on weekdays within working hours (UTC), excluding existing holds. |
| `create_tentative_hold` | workspace | write | readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False | bearer token + audit log | Place a tentative calendar hold for an interview slot (idempotent). |
| `create_email_draft` | workspace | write | readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False | bearer token + audit log | Save an email draft for the freelancer to review (never sends). |

Write tools also take `idempotency_key` (required) and `dry_run` (returns exactly what would be sent and the Connects cost). Every call is written to the append-only `audit_log` table (user, tool, PII-masked arguments, result, trace id).

Resources (portfolio): `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://item/{id}`.
Prompts (portfolio): `answer_screening_question`, `draft_cover_letter`, `summarise_skill_evidence`.

## Third-party servers (not written by us)

| Server | Used for | Trust rationale |
|---|---|---|
| Official Upwork MCP (`https://mcp.upwork.com/mcp`, OAuth 2.1) | Live mode behind `upwork_live` adapter | Operated by the platform itself, so it is the only sanctioned way to act on Upwork; we only create drafts and the user confirms on Upwork. |
| GitHub MCP (`https://api.githubcopilot.com/mcp/`, read-only PAT) | Repo ingestion for the portfolio (README + code) | Official GitHub server; read-only token scoped to the user's public repos, so it cannot change anything. |
