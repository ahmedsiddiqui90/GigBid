"""Generate docs/TOOLS.md from the live MCP server registries. Run: python -m scripts.gen_tools_doc"""
import asyncio
import sys

from mcp.shared.memory import create_connected_server_and_client_session

AUTH = {"portfolio": "bearer token (HTTP) / none (stdio)", "marketplace": "bearer token + per-user rate limit + audit log",
        "workspace": "bearer token + audit log"}
HEAD = """# MCP tools

Generated from the server registries (`python -m scripts.gen_tools_doc`). Agents never call GigSim, Upwork, the database
or files directly: every capability is one of these tools, and each agent gets only the tools named in
`agent/config.yaml` (`mcp.allowlists`).

| Tool | Server | R/W | Annotations | Auth | Description |
|---|---|---|---|---|---|
"""
TAIL = """
Write tools also take `idempotency_key` (required) and `dry_run` (returns exactly what would be sent and the Connects
cost). Every call is written to the append-only `audit_log` table (user, tool, PII-masked arguments, result, trace id).

Resources (portfolio): `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://item/{id}`.
Prompts (portfolio): `answer_screening_question`, `draft_cover_letter`, `summarise_skill_evidence`.

## Third-party servers (not written by us)

| Server | Used for | Trust rationale |
|---|---|---|
| Official Upwork MCP (`https://mcp.upwork.com/mcp`, OAuth 2.1) | Live mode behind the `upwork_live` adapter | Operated by the platform itself, so it is the only sanctioned way to act on Upwork; we only create drafts and the user confirms on Upwork. |
| GitHub MCP (`https://api.githubcopilot.com/mcp/`, read-only PAT) | Repo ingestion for the portfolio (README + code) | Official GitHub server; a read-only token scoped to the user's public repos cannot change anything. |
"""


async def main() -> None:
    rows = []
    for name in ("portfolio", "marketplace", "workspace"):
        mod = __import__(f"mcp_servers.{name}.server", fromlist=["mcp"])
        async with create_connected_server_and_client_session(mod.mcp._mcp_server) as s:
            for t in (await s.list_tools()).tools:
                a = t.annotations
                rw = "read" if a and a.readOnlyHint else "write"
                ann = ", ".join(f"{k}={v}" for k, v in (a.model_dump(exclude_none=True).items() if a else []) if k != "title")
                rows.append(f"| `{t.name}` | {name} | {rw} | {ann} | {AUTH[name]} | {t.description.splitlines()[0]} |")
    with open("docs/TOOLS.md", "w", encoding="utf-8") as f:
        f.write(HEAD + "\n".join(rows) + "\n" + TAIL)
    print(len(rows), "tools")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
