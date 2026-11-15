"""Structured hand-offs between agents (C3). Anything a later step decides on is one of these."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class JobSpec(BaseModel):
    job_id: str
    title: str
    category: str = "other"
    requirements: list[str] = Field(default_factory=list, description="3-7 specific checkable requirements")
    deliverables: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    budget_type: str = "fixed"
    budget_min: float | None = None
    budget_max: float | None = None
    timeline: str | None = None
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list)


class RiskReport(BaseModel):
    score: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list)
    explanation: str = ""
    injection_text: list[str] = Field(default_factory=list, description="sentences in the post that try to instruct an AI")
    client_summary: str = ""


class RequirementMatch(BaseModel):
    requirement: str
    evidence_ids: list[str] = Field(default_factory=list)
    covered: bool = False


class FitReport(BaseModel):
    score: float = Field(ge=0, le=1)
    matrix: list[RequirementMatch] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class BidDecision(BaseModel):
    action: Literal["bid", "watch", "skip"]
    reasons: list[str] = Field(default_factory=list)


class PriceQuote(BaseModel):
    amount: float
    currency: str = "USD"
    connects_cost: int = 0
    connects_balance: int | None = None
    worth_it: bool = True
    rationale: str = ""


class ProposalDraft(BaseModel):
    cover_letter: str = Field(description="120-220 words; experience claims cite evidence ids in [brackets]")
    screening_answers: list[str] = Field(default_factory=list)
    cited_ids: list[str] = Field(default_factory=list)


class Critique(BaseModel):
    score: float = Field(ge=0, le=1)
    passed: bool
    issues: list[str] = Field(default_factory=list)


class ComplianceVerdict(BaseModel):
    passed: bool
    blocked: bool = False
    reason: str = ""
    edits: list[str] = Field(default_factory=list)


class LiaisonOutput(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal", "other"]
    reply: str
    offer_slots: bool = False
