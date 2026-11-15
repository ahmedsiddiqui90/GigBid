from fastapi import APIRouter, Depends, HTTPException, Response

from agent import db
from apps.api.auth.security import COOKIE, create_session, current_user, hash_password, verify_password
from apps.api.schemas.models import LoginIn, Me, SignupIn

router = APIRouter(prefix="/api/auth", tags=["auth"])


def to_me(u: dict) -> Me:
    return Me(id=u["id"], email=u["email"], name=u.get("name"), persona_id=u.get("persona_id"),
              freelancer_id=u.get("freelancer_id"), marketplace=u.get("marketplace"), settings=u.get("settings") or {},
              onboarded=bool(u.get("persona_id")))


def _cookie(resp: Response, token: str) -> None:
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=7 * 86400)


@router.post("/signup", response_model=Me)
async def signup(body: SignupIn, resp: Response) -> Me:
    if await db.fetchone("SELECT id FROM users WHERE email=%s", body.email.lower()):
        raise HTTPException(409, "email already registered")
    await db.execute("INSERT INTO users (email, password_hash, name) VALUES (%s,%s,%s)", body.email.lower(),
                     hash_password(body.password), body.name)
    u = await db.fetchone("SELECT * FROM users WHERE email=%s", body.email.lower())
    _cookie(resp, await create_session(u["id"]))
    return to_me(u)


@router.post("/login", response_model=Me)
async def login(body: LoginIn, resp: Response) -> Me:
    u = await db.fetchone("SELECT * FROM users WHERE email=%s", body.email.lower())
    if not u or not verify_password(body.password, u["password_hash"]):
        raise HTTPException(401, "wrong email or password")
    _cookie(resp, await create_session(u["id"]))
    return to_me(u)


@router.post("/logout")
async def logout(resp: Response, user: dict = Depends(current_user)) -> dict:
    await db.execute("DELETE FROM sessions WHERE user_id=%s", user["id"])
    resp.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/me", response_model=Me)
async def me(user: dict = Depends(current_user)) -> Me:
    return to_me(user)
