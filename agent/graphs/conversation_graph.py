"""Conversation graph (one thread per client conversation).

load_thread -> client_liaison (classify intent, draft reply, fetch free slots) -> compliance
  -> message_approval [interrupt()] -> send_reply (+ tentative calendar hold) -> END
Terminal statuses (blocked, rejected, waiting_marketplace) end the run early.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from agent.nodes.client_liaison import (
    client_liaison,
    conversation_compliance,
    load_thread,
    message_approval,
    send_reply,
)
from agent.state import ConversationState

STOP = ("blocked", "rejected", "waiting_marketplace", "needs_attention")


def _next(target: str):
    return lambda s: END if s.get("status") in STOP else target


def build_conversation_graph(checkpointer=None, store=None):
    g = StateGraph(ConversationState)
    retry = RetryPolicy(max_attempts=3, initial_interval=1.0)
    g.add_node("load_thread", load_thread, retry_policy=retry)
    g.add_node("client_liaison", client_liaison, retry_policy=retry)
    g.add_node("conversation_compliance", conversation_compliance)
    g.add_node("message_approval", message_approval)
    g.add_node("send_reply", send_reply, retry_policy=retry)
    g.add_edge(START, "load_thread")
    g.add_conditional_edges("load_thread", _next("client_liaison"), ["client_liaison", END])
    g.add_edge("client_liaison", "conversation_compliance")
    g.add_conditional_edges("conversation_compliance", _next("message_approval"), ["message_approval", END])
    g.add_conditional_edges("message_approval", _next("send_reply"), ["send_reply", END])
    g.add_edge("send_reply", END)
    return g.compile(checkpointer=checkpointer, store=store)
