"""Onboarding: persona/own profile, marketplace connection (GigSim or Upwork OAuth 2.1 + PKCE), uploads,
rates, filters and weekly Connects budget."""
from __future__ import annotations

import base64
import hashlib
import secrets
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import RedirectResponse

from agent import db
from agent.settings import ROOT, env
from apps.api.auth.security import current_user, encrypt
from apps.api.queue import enqueue
from apps.api.schemas.models import OnboardingIn

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])
UPLOADS = ROOT / "data" / "uploads"
_pkce: dict[str, tuple[int, str]] = {}


@router.post("")
async def onboard(body: OnboardingIn, user: dict = Depends(current_user)) -> dict:
    settings = {**(user.get("settings") or {}), "hourly_rate": body.hourly_rate, "floor_rate": body.floor_rate,
                "weekly_connects": body.weekly_connects, "autonomy": "auto_skip_low_fit"}
    await db.execute("UPDATE users SET persona_id=%s, freelancer_id=%s, marketplace=%s, settings=%s WHERE id=%s",
                     body.persona_id, f"fl-{user['id']}-{body.persona_id}", body.marketplace, db.j(settings), user["id"])
    await db.execute("DELETE FROM saved_searches WHERE user_id=%s", user["id"])
    await db.execute("INSERT INTO saved_searches (user_id, query, category, every_minutes) VALUES (%s,%s,%s,%s)",
                     user["id"], body.search_query, body.search_category, body.every_minutes)
    await enqueue("scout_user", user["id"], job_id=f"scout:{user['id']}:onboard")
    return {"ok": True}


@router.post("/upload")
async def upload(file: UploadFile, user: dict = Depends(current_user)) -> dict:
    name = Path(file.filename or "upload").name
    if Path(name).suffix.lower() not in (".pdf", ".md", ".txt", ".json"):
        raise HTTPException(400, "upload a PDF CV, Markdown case study, text file or proposals JSON")
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(413, "file too large (5 MB max)")
    d = UPLOADS / str(user["id"])
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(data)
    await enqueue("reindex_user", user["id"], job_id=f"reindex:{user['id']}:{hashlib.md5(data).hexdigest()[:8]}")
    return {"ok": True, "file": name, "note": "re-indexing in the background"}


@router.get("/upwork/start")
async def upwork_start(user: dict = Depends(current_user)):
    e = env()
    if not e.upwork_client_id:
        raise HTTPException(400, "Live mode needs an Upwork API key (UPWORK_CLIENT_ID). See docs/RUNBOOK.md.")
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    _pkce[state] = (user["id"], verifier)
    q = urlencode({"response_type": "code", "client_id": e.upwork_client_id, "redirect_uri": e.upwork_redirect_uri,
                   "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
    return RedirectResponse(f"https://www.upwork.com/ab/account-security/oauth2/authorize?{q}")


@router.get("/upwork/callback")
async def upwork_callback(code: str, state: str):
    if state not in _pkce:
        raise HTTPException(400, "invalid OAuth state")
    uid, verifier = _pkce.pop(state)
    e = env()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post("https://www.upwork.com/api/v3/oauth2/token", data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": e.upwork_redirect_uri,
            "client_id": e.upwork_client_id, "client_secret": e.upwork_client_secret, "code_verifier": verifier})
    if r.status_code != 200:
        raise HTTPException(400, "Upwork token exchange failed")
    await db.execute("INSERT INTO oauth_tokens (user_id, provider, ciphertext) VALUES (%s,'upwork',%s) "
                     "ON CONFLICT (user_id, provider) DO UPDATE SET ciphertext=EXCLUDED.ciphertext, updated_at=now()",
                     uid, encrypt(r.text))  # token JSON stored encrypted, never logged
    return RedirectResponse("/settings?connected=upwork")
