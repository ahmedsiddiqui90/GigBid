"""Settings, saved searches, memory viewer, analytics."""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends

from agent import db
from agent.memory.store import delete_memory, list_memory, open_store
from apps.api.auth.security import current_user
from apps.api.schemas.models import SavedSearchIn, SettingsIn

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
async def get_settings(user: dict = Depends(current_user)) -> dict:
    searches = await db.fetch("SELECT id, query, category, every_minutes, last_run FROM saved_searches WHERE user_id=%s",
                              user["id"])
    connected = [r["provider"] for r in await db.fetch("SELECT provider FROM oauth_tokens WHERE user_id=%s", user["id"])]
    return {"settings": user.get("settings") or {}, "persona_id": user.get("persona_id"), "marketplace": user.get("marketplace"),
            "saved_searches": searches, "connected_accounts": ["gigsim"] + connected}


@router.put("/settings")
async def put_settings(body: SettingsIn, user: dict = Depends(current_user)) -> dict:
    s = {**(user.get("settings") or {}), **body.model_dump(exclude_none=True)}
    await db.execute("UPDATE users SET settings=%s WHERE id=%s", db.j(s), user["id"])
    return {"settings": s}


@router.post("/saved-searches")
async def add_search(body: SavedSearchIn, user: dict = Depends(current_user)) -> dict:
    await db.execute("INSERT INTO saved_searches (user_id, query, category, every_minutes) VALUES (%s,%s,%s,%s)",
                     user["id"], body.query, body.category, body.every_minutes)
    return {"ok": True}


@router.delete("/saved-searches/{sid}")
async def del_search(sid: int, user: dict = Depends(current_user)) -> dict:
    await db.execute("DELETE FROM saved_searches WHERE id=%s AND user_id=%s", sid, user["id"])
    return {"ok": True}


@router.get("/memory")
async def memory(user: dict = Depends(current_user)) -> dict:
    async with open_store() as store:
        return await list_memory(store, str(user["id"]))


@router.delete("/memory/{ns}/{key}")
async def forget(ns: str, key: str, user: dict = Depends(current_user)) -> dict:
    async with open_store() as store:
        await delete_memory(store, str(user["id"]), ns, key)
    return {"ok": True}


@router.get("/analytics")
async def analytics(user: dict = Depends(current_user)) -> dict:
    jobs = await db.fetch("SELECT job, stage, status, decision, analysis FROM jobs WHERE user_id=%s", user["id"])
    by_cat: dict[str, dict] = {}
    connects_spent = 0
    for r in jobs:
        cat = (r["job"] or {}).get("category", "other")
        c = by_cat.setdefault(cat, {"analysed": 0, "submitted": 0, "replied": 0, "hired": 0})
        c["analysed"] += 1
        if r["stage"] in ("submitted", "viewed", "replied", "interview", "hired", "lost"):
            c["submitted"] += 1
            connects_spent += (r["job"] or {}).get("connects_cost", 0)
        if r["stage"] in ("replied", "interview", "hired"):
            c["replied"] += 1
        if r["stage"] == "hired":
            c["hired"] += 1
    for c in by_cat.values():
        c["reply_rate"] = round(c["replied"] / c["submitted"], 3) if c["submitted"] else None
        c["hire_rate"] = round(c["hired"] / c["submitted"], 3) if c["submitted"] else None
    runs = await db.fetch("SELECT graph, status, usage, EXTRACT(EPOCH FROM (finished_at-started_at)) AS secs FROM runs "
                          "WHERE user_id=%s AND finished_at IS NOT NULL", user["id"])
    costs = [sum(u.get("cost_usd", 0) for u in (r["usage"] or [])) for r in runs]
    lat = sorted(float(r["secs"] or 0) for r in runs)
    rej = Counter((a["resolution"] or {}).get("reason", "") for a in await db.fetch(
        "SELECT resolution FROM approvals WHERE user_id=%s AND resolution->>'action'='reject'", user["id"]))
    skips = Counter(((r["analysis"] or {}).get("decision") or {}).get("reasons", ["?"])[0].split(":")[0]
                    for r in jobs if r["decision"] == "skip")
    return {"by_category": by_cat, "connects_spent": connects_spent,
            "cost_per_run_usd": round(sum(costs) / len(costs), 5) if costs else None,
            "p50_latency_s": lat[len(lat) // 2] if lat else None, "p95_latency_s": lat[int(len(lat) * 0.95)] if lat else None,
            "top_rejection_reasons": rej.most_common(5), "top_skip_reasons": skips.most_common(5),
            "ab_test": await _ab(user["id"])}


async def _ab(uid: int) -> dict:
    rows = await db.fetch("SELECT analysis->>'strategy' AS arm, stage FROM jobs WHERE user_id=%s AND stage IS NOT NULL", uid)
    out: dict[str, dict] = {}
    for r in rows:
        a = out.setdefault(r["arm"] or "unknown", {"submitted": 0, "replied": 0})
        if r["stage"] != "drafted":
            a["submitted"] += 1
        if r["stage"] in ("replied", "interview", "hired"):
            a["replied"] += 1
    return out
