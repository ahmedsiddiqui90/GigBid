import asyncio
import os
import sys

import pytest

os.environ.setdefault("MODEL_PROFILE", "offline")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
def gigsim_adapter(monkeypatch):
    """Marketplace adapter wired to an in-process GigSim (no network)."""
    import httpx

    from gigsim.app import app as gigsim_app
    from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter

    def make(*_a, **_k):
        return GigSimAdapter(base_url="http://gigsim.test", transport=httpx.ASGITransport(app=gigsim_app))

    import mcp_servers.marketplace.server as srv

    monkeypatch.setattr(srv, "get_adapter", make)
    return make
