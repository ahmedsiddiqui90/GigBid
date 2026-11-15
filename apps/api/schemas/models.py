"""Request/response models (drive the generated TypeScript client)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SignupIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(default="", max_length=100)


class LoginIn(BaseModel):
    email: str
    password: str


class Me(BaseModel):
    id: int
    email: str
    name: str | None = None
    persona_id: str | None = None
    freelancer_id: str | None = None
    marketplace: str | None = None
    settings: dict[str, Any] = {}
    onboarded: bool


class OnboardingIn(BaseModel):
    persona_id: Literal["ai_ml", "fullstack", "data_analyst"]
    marketplace: Literal["gigsim", "upwork_live"] = "gigsim"
    hourly_rate: float = Field(gt=0, le=1000)
    floor_rate: float = Field(gt=0, le=1000)
    weekly_connects: int = Field(ge=0, le=1000, default=80)
    search_query: str = Field(default="", max_length=200)
    search_category: str | None = None
    every_minutes: int = Field(default=30, ge=5, le=1440)


class JobRow(BaseModel):
    job_id: str
    title: str
    category: str | None = None
    status: str
    decision: str | None = None
    fit: float | None = None
    risk: float | None = None
    risk_flags: list[str] = []
    price: float | None = None
    connects: int | None = None
    budget: dict[str, Any] = {}
    stage: str | None = None
    updated_at: str | None = None


class ResolveIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    text: str | None = Field(default=None, max_length=5000)
    answers: list[str] | None = None
    reason: str | None = Field(default=None, max_length=1000)


class SettingsIn(BaseModel):
    autonomy: Literal["manual", "auto_skip_low_fit"] = "auto_skip_low_fit"
    hourly_rate: float | None = None
    floor_rate: float | None = None
    weekly_connects: int | None = None
    max_tokens_per_thread: int | None = None


class SavedSearchIn(BaseModel):
    query: str = Field(max_length=200)
    category: str | None = None
    every_minutes: int = Field(default=30, ge=5, le=1440)


class RegenerateIn(BaseModel):
    paragraph: str = Field(min_length=1, max_length=3000)
    instruction: str = Field(default="Make it more specific to the client.", max_length=300)


class Health(BaseModel):
    api: bool
    marketplace: bool
    database: bool
    worker_queue: bool
    model_profile: str
    marketplace_adapter: str
