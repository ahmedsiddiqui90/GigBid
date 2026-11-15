"""Run the API with uvicorn on an event loop psycopg supports (selector loop on Windows).
Usage: python -m scripts.serve_api [--port 8000]"""
import argparse
import asyncio
import sys

import uvicorn

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="0.0.0.0")
    a = ap.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    from apps.api.main import app

    server = uvicorn.Server(uvicorn.Config(app, host=a.host, port=a.port, loop="none"))
    asyncio.run(server.serve())
