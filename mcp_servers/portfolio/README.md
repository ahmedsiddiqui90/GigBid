# GigBid Portfolio MCP server

An MCP server that lets any assistant (Claude Desktop, Cursor, your own agent) search **your** freelance
portfolio for evidence: case studies, repo READMEs and code, client reviews and past proposals with outcomes.
Read-only. Built with the official MCP Python SDK.

## Install and run

```bash
# from the GigBid repository
uvx --from git+https://github.com/<you>/gigbid gigbid-portfolio-mcp --dir ./my_portfolio
# or, inside a clone
pip install -e . && gigbid-portfolio-mcp --persona ai_ml          # bundled synthetic demo persona
gigbid-portfolio-mcp --dir ./my_portfolio --http                     # streamable HTTP on :8101 (bearer MCP_BEARER_TOKEN)
```

Claude Desktop (`claude_desktop_config.json`):

```json
{ "mcpServers": { "portfolio": { "command": "uvx",
  "args": ["--from", "git+https://github.com/<you>/gigbid", "gigbid-portfolio-mcp", "--dir", "C:/me/portfolio"] } } }
```

## Your portfolio folder

Any mix of: `*.md` case studies (optional YAML front matter: `id`, `type`, `project`, `skills`, `date`,
`client_industry`), `*.pdf` CV, `repos/<name>/README.md`, `reviews.json`, `past_proposals.json`
(`[{"id","text","outcome": "won|replied|ignored", ...}]`). Embeddings run locally on CPU (BAAI/bge-small-en-v1.5).

## Tools, resources, prompts

| Tool | What it returns |
|---|---|
| `search_evidence(requirement, k, filters)` | evidence items with id, type, source project, date, outcome, snippet, score |
| `get_case_study(id)` | one item in full |
| `list_skills()` | skills your portfolio proves, with counts |

Resources: `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://item/{id}`.
Prompts: *Answer a screening question from my portfolio*, *Draft a cover letter for this job*,
*Summarise my evidence for a skill*.
