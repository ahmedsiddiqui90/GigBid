"""Typed graph state (C2).

Three things are kept apart:
  * State (fields below): what this job / conversation needs right now.
  * Execution trace (`trace`, plus runs/run_steps tables and LangSmith): every tool call and observation.
  * Long-term memory (agent/memory/store.py): only promoted knowledge, written by explicit rules.
Parallel branches write disjoint keys; list fields that several nodes append to use reducers.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class BidState(TypedDict, total=False):
    # identity
    user_id: int
    persona: str
    freelancer_id: str
    floor_rate: float
    hourly_rate: float
    job_id: str
    run_id: str
    trace_id: str
    strategy: str
    # inputs / analyses (written by parallel branches: disjoint keys)
    job: dict[str, Any]
    client: dict[str, Any]
    job_spec: dict[str, Any]
    risk: dict[str, Any]
    fit: dict[str, Any]
    evidence: list[dict[str, Any]]
    # decisions and drafts
    decision: dict[str, Any]
    price: dict[str, Any]
    draft: dict[str, Any]
    verification: dict[str, Any]
    critique: dict[str, Any]
    revisions: int
    compliance: dict[str, Any]
    preview: dict[str, Any]
    approval: dict[str, Any]
    submission: dict[str, Any]
    status: str
    # reducers
    usage: Annotated[list[dict], operator.add]
    trace: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]
    degraded: Annotated[list[str], operator.add]
    steps: Annotated[int, operator.add]


class ConversationState(TypedDict, total=False):
    user_id: int
    persona: str
    freelancer_id: str
    thread_id: str
    run_id: str
    trace_id: str
    thread: dict[str, Any]
    intent: str
    reply: str
    slots: list[dict]
    offer_slots: bool
    compliance: dict[str, Any]
    approval: dict[str, Any]
    sent: dict[str, Any]
    status: str
    usage: Annotated[list[dict], operator.add]
    trace: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]
    steps: Annotated[int, operator.add]
