"""Postgres access (psycopg 3 async pool) and the application schema."""
from __future__ import annotations

import json
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from agent.settings import env

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, name TEXT,
  persona_id TEXT, freelancer_id TEXT, marketplace TEXT DEFAULT 'gigsim',
  settings JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INT REFERENCES users(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS oauth_tokens (user_id INT REFERENCES users(id) ON DELETE CASCADE, provider TEXT,
  ciphertext TEXT NOT NULL, updated_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY (user_id, provider));
CREATE TABLE IF NOT EXISTS saved_searches (id SERIAL PRIMARY KEY, user_id INT REFERENCES users(id) ON DELETE CASCADE,
  query TEXT NOT NULL, category TEXT, every_minutes INT NOT NULL DEFAULT 30, last_run TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS jobs (user_id INT REFERENCES users(id) ON DELETE CASCADE, job_id TEXT,
  dedupe_hash TEXT, job JSONB NOT NULL, status TEXT NOT NULL DEFAULT 'queued', thread_id TEXT,
  decision TEXT, fit REAL, risk REAL, price REAL, connects INT, analysis JSONB DEFAULT '{}'::jsonb,
  stage TEXT, proposal_id TEXT, updated_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY (user_id, job_id));
CREATE INDEX IF NOT EXISTS jobs_dedupe ON jobs (user_id, dedupe_hash);
CREATE TABLE IF NOT EXISTS approvals (id SERIAL PRIMARY KEY, user_id INT REFERENCES users(id) ON DELETE CASCADE,
  thread_id TEXT NOT NULL, kind TEXT NOT NULL, ref_id TEXT, payload JSONB NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  resolution JSONB, created_at TIMESTAMPTZ DEFAULT now(), resolved_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, user_id INT, thread_id TEXT, graph TEXT, ref_id TEXT,
  status TEXT, trace_id TEXT, started_at TIMESTAMPTZ DEFAULT now(), finished_at TIMESTAMPTZ,
  usage JSONB DEFAULT '[]'::jsonb, error TEXT);
CREATE TABLE IF NOT EXISTS run_steps (id SERIAL PRIMARY KEY, run_id TEXT, node TEXT, ts TIMESTAMPTZ DEFAULT now(),
  data JSONB);
CREATE TABLE IF NOT EXISTS edits (id SERIAL PRIMARY KEY, user_id INT, job_id TEXT, before TEXT, after TEXT,
  patterns JSONB, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS idempotency (key TEXT PRIMARY KEY, server TEXT, result JSONB, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS audit_log (id BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ DEFAULT now(), user_id TEXT,
  server TEXT, tool TEXT, args JSONB, result JSONB, trace_id TEXT);
CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_log_no_change ON audit_log;
CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
CREATE TABLE IF NOT EXISTS workspace_holds (id SERIAL PRIMARY KEY, user_id TEXT, start_ts TIMESTAMPTZ, end_ts TIMESTAMPTZ,
  title TEXT, idem TEXT UNIQUE, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS workspace_drafts (id SERIAL PRIMARY KEY, user_id TEXT, recipient TEXT, subject TEXT, body TEXT,
  created_at TIMESTAMPTZ DEFAULT now());
"""

_pool: AsyncConnectionPool | None = None


async def pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(env().database_url, min_size=1, max_size=10, open=False,
                                    kwargs={"autocommit": True, "row_factory": dict_row})
        await _pool.open()
    return _pool


async def init_schema() -> None:
    p = await pool()
    async with p.connection() as c:
        await c.execute(SCHEMA)


async def fetch(sql: str, *args: Any) -> list[dict]:
    p = await pool()
    async with p.connection() as c:
        cur = await c.execute(sql, args)
        return await cur.fetchall() if cur.description else []


async def fetchone(sql: str, *args: Any) -> dict | None:
    rows = await fetch(sql, *args)
    return rows[0] if rows else None


async def execute(sql: str, *args: Any) -> None:
    p = await pool()
    async with p.connection() as c:
        await c.execute(sql, args)


def j(obj: Any) -> str:
    """Serialise to JSON for JSONB parameters."""
    return json.dumps(obj, default=str)
