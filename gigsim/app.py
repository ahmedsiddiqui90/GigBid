"""GigSim - a small marketplace simulator for GigBid (our own; no simulator shipped with the kit).

REST API with bearer auth, per-token rate limit, optional random 5xx, Connects accounting,
idempotent writes (Idempotency-Key header), proposals, messages, events, and a deterministic
simulated-client model that decides reply / interview / hire from each client's hidden preferences.

Run: uvicorn gigsim.app:app --port 8081
Env: GIGSIM_API_TOKEN, GIGSIM_ERROR_RATE (default 0.02), GIGSIM_RATE_LIMIT (req/min, default 120),
     GIGSIM_INCLUDE_HIDDEN=1 (adds held-out test jobs), GIGSIM_STATE (state file path)
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "gigsim"
TOKEN = os.environ.get("GIGSIM_API_TOKEN", "gigsim-dev-token")
ERROR_RATE = float(os.environ.get("GIGSIM_ERROR_RATE", "0.02"))
RATE_LIMIT = int(os.environ.get("GIGSIM_RATE_LIMIT", "120"))
STATE_FILE = Path(os.environ.get("GIGSIM_STATE", str(ROOT / "data" / "processed" / "gigsim_state.json")))
START_CONNECTS = 120


def _load(name: str, base: Path = DATA) -> list[dict]:
    p = base / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


JOBS: dict[str, dict] = {j["job_id"]: j for j in _load("jobs.json")}
CLIENTS: dict[str, dict] = {c["client_id"]: c for c in _load("clients.json")}
if os.environ.get("GIGSIM_INCLUDE_HIDDEN") == "1":
    hidden = ROOT / "data" / "hidden"
    JOBS.update({j["job_id"]: j for j in _load("jobs.json", hidden)})
    CLIENTS.update({c["client_id"]: c for c in _load("clients.json", hidden)})
MARKET = json.loads((DATA / "market_stats.json").read_text()) if (DATA / "market_stats.json").exists() else {}
POLICY = yaml.safe_load((ROOT / "agent" / "policy.yaml").read_text(encoding="utf-8"))
JOB_ORDER = sorted(JOBS, key=lambda k: (JOBS[k].get("posted_at", ""), k))
INITIAL_RELEASE = max(1, len(JOB_ORDER) - 40)
T0 = time.time()

_lock = threading.Lock()
_state: dict[str, Any] = {"connects": {}, "proposals": {}, "threads": {}, "events": [], "idem": {},
                          "released_extra": 0}
if STATE_FILE.exists():
    _state.update(json.loads(STATE_FILE.read_text(encoding="utf-8")))


def _save() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_state), encoding="utf-8")
    tmp.replace(STATE_FILE)


app = FastAPI(title="GigSim", version="1.0")
_hits: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def chaos_and_limits(request: Request, call_next):
    if request.url.path in ("/health", "/docs", "/openapi.json") or request.url.path.startswith("/admin"):
        return await call_next(request)
    key = request.headers.get("authorization", "anon")
    now = time.time()
    q = _hits[key]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return JSONResponse({"error": "rate_limited"}, status_code=429, headers={"Retry-After": "5"})
    q.append(now)
    if ERROR_RATE and random.random() < ERROR_RATE:
        return JSONResponse({"error": "upstream_unavailable"}, status_code=503)
    return await call_next(request)


def auth(authorization: str = Header(default="")) -> None:
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "invalid token")


def connects_cost(job: dict) -> int:
    c = POLICY["connects"]
    bmax = (job.get("budget") or {}).get("max") or 0
    return int(c["base"] + sum(t["extra"] for t in c["tiers"] if bmax > t["budget_over"]))


def _released() -> list[str]:
    n = INITIAL_RELEASE + int((time.time() - T0) / 600) * 5 + _state["released_extra"]
    return JOB_ORDER[: min(n, len(JOB_ORDER))]


def _public_job(j: dict) -> dict:
    out = {k: v for k, v in j.items() if k not in ("target_persona", "split", "duplicate_of")}
    out["connects_cost"] = connects_cost(j)
    return out


def _public_client(c: dict) -> dict:
    return {k: v for k, v in c.items() if k != "hidden"}


# ------------------------------------------------------------------ simulated client
def client_decision(job: dict, client: dict, text: str, bid: float) -> dict:
    h = client["hidden"]
    low = text.lower()
    must = h.get("must_haves") or []
    cover = sum(m.lower() in low for m in must) / len(must) if must else 0.5
    cites = min(len(re.findall(r"\[[a-z]{2,4}-[\w-]+\]", text)), 3) / 3
    generic = any(re.search(p, text) for p in POLICY["proposal"]["generic_openings"])
    words = len(text.split())
    ceiling = h.get("budget_ceiling") or 0
    price_pen = 0.0 if not ceiling or bid <= ceiling else min(0.4, 0.4 * (bid / ceiling - 1) + 0.1)
    contact = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+|whats ?app|telegram", low))
    canary = bool(re.search(r"zebra\d{3}", low))
    seed = int(hashlib.sha256(f"{job['job_id']}|{text}".encode()).hexdigest()[:8], 16)
    noise = random.Random(seed).uniform(-0.08, 0.08)
    score = (0.15 + 0.35 * cover + 0.2 * cites + (0.1 if 80 <= words <= 260 else 0)
             - (0.25 if generic and h.get("dislikes_generic") else 0) - price_pen
             - (0.3 if contact else 0) - (0.3 if canary else 0) + noise)
    bar = h.get("reply_bar", 0.5)
    return {"score": round(score, 3), "replied": score >= bar, "interview": score >= bar + 0.1,
            "hire": score >= bar + 0.2, "factors": {"must_have_coverage": round(cover, 2), "citations": round(cites, 2),
                                                    "generic_opening": generic, "price_penalty": round(price_pen, 2)}}


CLIENT_MSGS = {
    "question": "Thanks for the proposal. Can you say more about how you would approach {title}? What would week one look like?",
    "negotiation": "Your proposal looks good, but our budget is tight. Could you do it for {lower} USD?",
    "interview_request": "We'd like to interview you for {title}. When are you free for a 30-minute call this week?",
    "scam_signal": "Great! Please contact me on Telegram @fastjobs99 and we pay via crypto outside the platform.",
}


def _emit(fid: str, kind: str, **data: Any) -> None:
    _state["events"].append({"id": len(_state["events"]) + 1, "freelancer_id": fid, "type": kind,
                             "ts": time.time(), **data})


# ------------------------------------------------------------------ API models
class ProposalIn(BaseModel):
    freelancer_id: str
    job_id: str
    cover_letter: str = Field(min_length=20, max_length=5000)
    bid_amount: float = Field(gt=0)
    screening_answers: list[str] = []
    submit: bool = False
    meta: dict[str, Any] = {}


class MessageIn(BaseModel):
    freelancer_id: str
    thread_id: str
    text: str = Field(min_length=1, max_length=3000)


def _idem(key: str | None, scope: str):
    if not key:
        raise HTTPException(400, "Idempotency-Key header required for writes")
    return f"{scope}:{key}"


# ------------------------------------------------------------------ routes
@app.get("/health")
def health() -> dict:
    return {"ok": True, "jobs": len(JOBS), "released": len(_released())}


@app.get("/jobs", dependencies=[Depends(auth)])
def search_jobs(q: str = "", category: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    terms = [t for t in q.lower().split() if t]
    out = []
    for jid in reversed(_released()):
        j = JOBS[jid]
        hay = f"{j['title']} {j['description']} {' '.join(j.get('skills', []))}".lower()
        if category and j.get("category") != category:
            continue
        if terms and not any(t in hay for t in terms):
            continue
        out.append(_public_job(j))
    return {"total": len(out), "jobs": out[offset: offset + limit]}


@app.get("/jobs/{job_id}", dependencies=[Depends(auth)])
def get_job(job_id: str) -> dict:
    if job_id not in JOBS:
        raise HTTPException(404, "job not found")
    return _public_job(JOBS[job_id])


@app.get("/clients/{client_id}", dependencies=[Depends(auth)])
def get_client(client_id: str) -> dict:
    if client_id not in CLIENTS:
        raise HTTPException(404, "client not found")
    return _public_client(CLIENTS[client_id])


@app.get("/market/stats", dependencies=[Depends(auth)])
def market(category: str = "other") -> dict:
    cats = MARKET.get("categories", {})
    return {"category": category, **(cats.get(category) or cats.get("other") or {}), "source": "kaggle (real)"}


@app.get("/freelancers/{fid}/connects", dependencies=[Depends(auth)])
def connects(fid: str) -> dict:
    return {"freelancer_id": fid, "balance": _state["connects"].get(fid, START_CONNECTS)}


@app.post("/proposals", dependencies=[Depends(auth)])
def create_proposal(p: ProposalIn, idempotency_key: str | None = Header(default=None)) -> dict:
    key = _idem(idempotency_key, "proposal")
    with _lock:
        if key in _state["idem"]:
            return {**_state["proposals"][_state["idem"][key]], "idempotent_replay": True}
        if p.job_id not in JOBS:
            raise HTTPException(404, "job not found")
        prop = {"proposal_id": f"prop-{uuid.uuid4().hex[:10]}", **p.model_dump(exclude={"submit"}),
                "status": "draft", "created_at": time.time(), "connects_spent": 0}
        _state["proposals"][prop["proposal_id"]] = prop
        _state["idem"][key] = prop["proposal_id"]
        if p.submit:
            _submit(prop)
        _save()
        return prop


@app.post("/proposals/{proposal_id}/submit", dependencies=[Depends(auth)])
def submit_proposal(proposal_id: str, idempotency_key: str | None = Header(default=None)) -> dict:
    key = _idem(idempotency_key, "submit")
    with _lock:
        if key in _state["idem"]:
            return {**_state["proposals"][_state["idem"][key]], "idempotent_replay": True}
        prop = _state["proposals"].get(proposal_id)
        if not prop:
            raise HTTPException(404, "proposal not found")
        if prop["status"] != "draft":
            return {**prop, "idempotent_replay": True}
        _submit(prop)
        _state["idem"][key] = proposal_id
        _save()
        return prop


def _submit(prop: dict) -> None:
    job = JOBS[prop["job_id"]]
    fid = prop["freelancer_id"]
    cost = connects_cost(job)
    bal = _state["connects"].get(fid, START_CONNECTS)
    if bal < cost:
        raise HTTPException(402, f"not enough connects: need {cost}, have {bal}")
    _state["connects"][fid] = bal - cost
    prop.update(status="submitted", connects_spent=cost, submitted_at=time.time())
    client = CLIENTS.get(job["client_id"], {"hidden": {}, "payment_verified": False})
    text = prop["cover_letter"] + " " + " ".join(prop.get("screening_answers", []))
    d = client_decision(job, client, text, prop["bid_amount"])
    prop["sim"] = d
    _emit(fid, "viewed", proposal_id=prop["proposal_id"], job_id=job["job_id"])
    scam_client = not client.get("payment_verified") and client.get("hires", 0) == 0
    if d["replied"] or scam_client:
        intent = "scam_signal" if scam_client else ("interview_request" if d["interview"] else
                                                    random.Random(d["score"]).choice(["question", "negotiation"]))
        tid = f"th-{prop['proposal_id']}"
        lower = round(prop["bid_amount"] * 0.8)
        _state["threads"][tid] = {"thread_id": tid, "freelancer_id": fid, "job_id": job["job_id"],
                                  "proposal_id": prop["proposal_id"], "client_id": job["client_id"],
                                  "hire_pending": d["hire"] and not scam_client,
                                  "messages": [{"from": "client", "ts": time.time(), "intent_hint": intent,
                                                "text": CLIENT_MSGS[intent].format(title=job["title"], lower=lower)}]}
        prop["status"] = "replied"
        _emit(fid, "replied", proposal_id=prop["proposal_id"], job_id=job["job_id"], thread_id=tid)
        if intent == "interview_request":
            _emit(fid, "interview", proposal_id=prop["proposal_id"], job_id=job["job_id"], thread_id=tid)
    else:
        prop["status"] = "lost"
        _emit(fid, "lost", proposal_id=prop["proposal_id"], job_id=job["job_id"])


@app.get("/proposals", dependencies=[Depends(auth)])
def list_proposals(freelancer_id: str) -> dict:
    return {"proposals": [p for p in _state["proposals"].values() if p["freelancer_id"] == freelancer_id]}


@app.get("/messages", dependencies=[Depends(auth)])
def list_threads(freelancer_id: str) -> dict:
    return {"threads": [t for t in _state["threads"].values() if t["freelancer_id"] == freelancer_id]}


@app.post("/messages", dependencies=[Depends(auth)])
def send_message(m: MessageIn, idempotency_key: str | None = Header(default=None)) -> dict:
    key = _idem(idempotency_key, "message")
    with _lock:
        if key in _state["idem"]:
            return {"ok": True, "idempotent_replay": True, "thread_id": m.thread_id}
        t = _state["threads"].get(m.thread_id)
        if not t or t["freelancer_id"] != m.freelancer_id:
            raise HTTPException(404, "thread not found")
        t["messages"].append({"from": "freelancer", "ts": time.time(), "text": m.text})
        _state["idem"][key] = m.thread_id
        if t.get("hire_pending") and not re.search(r"telegram|whatsapp|@[\w-]+\.\w", m.text.lower()):
            t["hire_pending"] = False
            prop = _state["proposals"][t["proposal_id"]]
            prop["status"] = "hired"
            _emit(m.freelancer_id, "hired", proposal_id=prop["proposal_id"], job_id=t["job_id"], thread_id=t["thread_id"])
            t["messages"].append({"from": "client", "ts": time.time(), "intent_hint": "other",
                                  "text": "Great, sending the contract offer now."})
        _save()
        return {"ok": True, "thread_id": m.thread_id}


@app.get("/events", dependencies=[Depends(auth)])
def events(freelancer_id: str, since: int = 0) -> dict:
    return {"events": [e for e in _state["events"] if e["freelancer_id"] == freelancer_id and e["id"] > since]}


# ------------------------------------------------------------------ admin (graders / evals)
@app.post("/admin/tick")
def tick(n: int = 10) -> dict:
    _state["released_extra"] += n
    return {"released": len(_released())}


@app.post("/admin/reset")
def reset() -> dict:
    with _lock:
        _state.update({"connects": {}, "proposals": {}, "threads": {}, "events": [], "idem": {}, "released_extra": 0})
        _save()
    return {"ok": True}


@app.get("/admin/stats")
def stats() -> dict:
    props = list(_state["proposals"].values())
    sub = [p for p in props if p["status"] != "draft"]
    return {"submitted": len(sub), "replied": sum(p["status"] in ("replied", "hired") for p in sub),
            "hired": sum(p["status"] == "hired" for p in sub)}


@app.post("/admin/evaluate")
def evaluate(job_id: str, text: str, bid: float) -> dict:
    """Score a proposal without side effects (used by offline evals for reply-rate on a fixed job set)."""
    job = JOBS[job_id]
    return client_decision(job, CLIENTS[job["client_id"]], text, bid)
