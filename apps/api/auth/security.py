"""Passwords (scrypt), session cookies, and encrypted OAuth token storage (Fernet, key from APP_SECRET_KEY)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from fastapi import Cookie, HTTPException

from agent import db
from agent.settings import env

COOKIE = "gb_session"


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return base64.b64encode(salt + h).decode()


def verify_password(pw: str, stored: str) -> bool:
    raw = base64.b64decode(stored.encode())
    salt, h = raw[:16], raw[16:]
    return hmac.compare_digest(h, hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1))


async def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    await db.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (%s,%s,%s)", token, user_id,
                     datetime.now(timezone.utc) + timedelta(days=7))
    return token


async def current_user(gb_session: str | None = Cookie(default=None)) -> dict:
    if not gb_session:
        raise HTTPException(401, "not signed in")
    u = await db.fetchone("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=%s AND s.expires_at > now()",
                          gb_session)
    if not u:
        raise HTTPException(401, "session expired")
    return u


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(env().app_secret_key.encode()).digest())
    return Fernet(key)


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
