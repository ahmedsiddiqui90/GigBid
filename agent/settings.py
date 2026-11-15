"""Typed settings: environment (.env) + agent/config.yaml + agent/policy.yaml."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


class Env(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    app_env: str = "development"
    app_secret_key: str = "dev-secret-change-me-dev-secret-change-me"
    database_url: str = "postgresql://postgres@localhost:5432/gigbid"
    redis_url: str = "redis://localhost:6379/0"
    model_profile: str | None = None
    marketplace_adapter: str | None = None
    gigsim_base_url: str = "http://localhost:8081"
    gigsim_api_token: str = "gigsim-dev-token"
    mcp_bearer_token: str = "mcp-dev-token"
    upwork_mcp_url: str = "https://mcp.upwork.com/mcp"
    upwork_client_id: str = ""
    upwork_client_secret: str = ""
    upwork_redirect_uri: str = "http://localhost:8000/api/onboarding/upwork/callback"
    github_mcp_url: str = "https://api.githubcopilot.com/mcp/"
    github_token: str = ""
    reviewer_email: str = "reviewer@gigbid.dev"
    reviewer_password: str = "reviewer-pass"


class Config(BaseModel):
    """Validated view of config.yaml (kept loose where structure is a simple dict)."""

    profile: str
    profiles: dict[str, dict[str, Any]]
    model_prices: dict[str, list[float]]
    llm: dict[str, Any]
    embeddings: dict[str, Any]
    reranker: dict[str, Any]
    retrieval: dict[str, Any]
    marketplace: dict[str, Any]
    mcp: dict[str, Any]
    thresholds: dict[str, float]
    budgets: dict[str, float]
    autonomy: dict[str, Any]
    memory: dict[str, Any]
    schedules: dict[str, Any]
    experiments: dict[str, Any]
    eval_gates: dict[str, float]


@lru_cache
def env() -> Env:
    return Env()


@lru_cache
def config() -> Config:
    data = yaml.safe_load((ROOT / "agent" / "config.yaml").read_text(encoding="utf-8"))
    cfg = Config(**data)
    e = env()
    if e.model_profile:
        cfg.profile = e.model_profile
    if e.marketplace_adapter:
        cfg.marketplace["adapter"] = e.marketplace_adapter
    if cfg.profile not in cfg.profiles:
        raise ValueError(f"unknown model profile {cfg.profile!r}")
    prof = cfg.profiles[cfg.profile]
    if prof.get("provider") != "heuristic" and not os.environ.get(prof.get("api_key_env", ""), ""):
        # No key for the chosen hosted profile: fall back to deterministic offline mode.
        cfg.profile = "offline"
    return cfg


@lru_cache
def policy() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "agent" / "policy.yaml").read_text(encoding="utf-8"))


def reload_all() -> None:
    env.cache_clear()
    config.cache_clear()
    policy.cache_clear()
