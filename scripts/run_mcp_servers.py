"""Run the three GigBid MCP servers (portfolio :8101, marketplace :8102, workspace :8103) in one process.
Usage: python -m scripts.run_mcp_servers [--only marketplace]"""
from __future__ import annotations

import argparse
import asyncio

import uvicorn

from agent import db
from agent.safety.pii import install_pii_logging

PORTS = {"portfolio": 8101, "marketplace": 8102, "workspace": 8103}


def _app(name: str):
    if name == "portfolio":
        from mcp_servers.portfolio.server import http_app
    elif name == "marketplace":
        from mcp_servers.marketplace.server import http_app
    else:
        from mcp_servers.workspace.server import http_app
    return http_app()


async def main(only: list[str]) -> None:
    install_pii_logging()
    await db.init_schema()
    servers = [uvicorn.Server(uvicorn.Config(_app(n), host="0.0.0.0", port=PORTS[n], log_level="warning")) for n in only]
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=list(PORTS))
    a = ap.parse_args()
    import sys

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main(a.only))
