"""Decide (bid / watch / skip) and Pricing Strategist. MCP: marketplace read (stats, client, Connects)."""
from __future__ import annotations

from agent.handoffs import BidDecision, PriceQuote
from agent.mcp_client import MarketplaceDown
from agent.memory.store import outcome_rate
from agent.nodes._base import node, tool
from agent.settings import config


def _store():
    try:
        from langgraph.config import get_store

        return get_store()
    except Exception:  # noqa: BLE001
        return None


def decide_rules(job: dict, risk: dict, fit: dict, floor_rate: float, reply_rate: float | None) -> BidDecision:
    t = config().thresholds
    reasons: list[str] = []
    budget_max = (job.get("budget") or {}).get("max") or 0
    if risk.get("score", 0) >= t["risk_skip"]:
        return BidDecision(action="skip", reasons=[f"risk {risk['score']:.2f} >= {t['risk_skip']}: {', '.join(risk.get('flags', []))}"])
    if budget_max and budget_max < floor_rate * 8:
        return BidDecision(action="skip", reasons=[f"budget ${budget_max} is below one day at the floor rate (${floor_rate}/h)"])
    bid_min = t["bid_fit_min"]
    if reply_rate is not None and reply_rate < 0.1:
        bid_min += 0.1
        reasons.append(f"outcome memory: reply rate {reply_rate:.0%} in this category, raising the bar")
    f = fit.get("score", 0)
    if f >= bid_min:
        return BidDecision(action="bid", reasons=reasons + [f"fit {f:.2f} >= {bid_min:.2f}"] + fit.get("reasons", []))
    if f >= t["watch_fit_min"]:
        return BidDecision(action="watch", reasons=reasons + [f"fit {f:.2f} between watch and bid thresholds"] + fit.get("reasons", []))
    return BidDecision(action="skip", reasons=reasons + [f"fit {f:.2f} < {t['watch_fit_min']}"] + fit.get("reasons", []))


@node("decide")
async def decide(state: dict) -> dict:
    if state.get("degraded"):
        return {"status": "waiting_marketplace"}
    rate = await outcome_rate(_store(), str(state.get("user_id")), state["job"].get("category", "other"))
    d = decide_rules(state["job"], state.get("risk", {}), state.get("fit", {}), state.get("floor_rate", 25), rate)
    out = {"decision": d.model_dump()}
    if d.action == "skip":
        out["status"] = "skipped"
    elif d.action == "watch":
        out["status"] = "watch"
    return out


def quote(job: dict, stats: dict, client: dict, floor: float, hourly: float, connects: int, balance: int | None,
          fit: float) -> PriceQuote:
    b = job.get("budget") or {}
    lo, hi = float(b.get("min") or 0), float(b.get("max") or 0)
    notes = []
    if b.get("type") == "hourly":
        market = stats.get("hourly_mid_median") or hourly
        amount = max(floor, min(hourly, hi or hourly))
        notes.append(f"hourly: my rate ${hourly}, floor ${floor}, market median ${market}/h, client range ${lo}-{hi}")
    else:
        target = lo + 0.6 * (hi - lo) if hi else (stats.get("fixed_budget_median") or 500)
        est_hours = (hi or target) / max(hourly, 1)
        amount = max(target, floor * est_hours * 0.8)
        amount = min(amount, hi * 1.05) if hi else amount
        notes.append(f"fixed: 60% into client range ${lo:.0f}-{hi:.0f}; floor check {floor}$/h x ~{est_hours:.0f}h")
        if stats.get("fixed_budget_median"):
            notes.append(f"market median fixed budget ${stats['fixed_budget_median']:.0f} (real Kaggle postings)")
    if client.get("total_spend"):
        notes.append(f"client has spent ${client['total_spend']} over {client.get('hires', 0)} hires")
    # Connects worth it? expected value = p(reply) * value vs Connects cost (~$0.15 each).
    p_reply = 0.1 + 0.4 * fit
    worth = (p_reply * amount * 0.1) > connects * 0.15 and (balance is None or balance >= connects)
    notes.append(f"Connects: {connects} (~${connects * 0.15:.2f}); balance {balance}; p(reply)~{p_reply:.2f}")
    return PriceQuote(amount=round(amount, 0), connects_cost=connects, connects_balance=balance, worth_it=worth,
                      rationale="; ".join(notes))


@node("pricing_strategist")
async def pricing_strategist(state: dict) -> dict:
    job = state["job"]
    trace = []
    try:
        stats, t1 = await tool(state, "pricing_strategist", "get_market_stats", {"category": job.get("category", "other")})
        bal, t2 = await tool(state, "pricing_strategist", "get_connects_balance", {"freelancer_id": state["freelancer_id"]})
        trace += [t1, t2]
    except MarketplaceDown as e:
        return {"status": "waiting_marketplace", "errors": [str(e)], "trace": trace}
    q = quote(job, stats, state.get("client", {}), state.get("floor_rate", 25), state.get("hourly_rate", 40),
              int(job.get("connects_cost", 6)), bal.get("balance"), state.get("fit", {}).get("score", 0))
    out = {"price": q.model_dump(), "trace": trace}
    if not q.worth_it:
        out["status"] = "skipped"
        out["decision"] = {"action": "skip", "reasons": ["Connects cost not worth it: " + q.rationale]}
    return out
