"""Smoke test: run the bid graph on a few dev jobs for a test user. Usage: python -m scripts.smoke_bid [job ids]"""
import asyncio
import sys

from agent import db
from agent.runner import graphs, resume, run_bid


async def ensure_user(persona="ai_ml", email="smoke@gigbid.dev"):
    await db.init_schema()
    u = await db.fetchone("SELECT * FROM users WHERE email=%s", email)
    if not u:
        await db.execute("INSERT INTO users (email, password_hash, name, persona_id, freelancer_id) VALUES (%s,'x','Smoke',%s,%s)",
                         email, persona, f"fl-smoke-{persona}")
        u = await db.fetchone("SELECT * FROM users WHERE email=%s", email)
    return u


async def main(ids):
    u = await ensure_user()
    async with graphs() as g:
        for jid in ids:
            await db.execute("INSERT INTO jobs (user_id, job_id, job) VALUES (%s,%s,'{}') ON CONFLICT DO NOTHING", u["id"], jid)
            r = await run_bid(g, u, jid)
            st = r.get("state", {})
            print(f"\n=== {jid}: {r['status']}  decision={st.get('decision')}")
            print("risk:", st.get("risk", {}).get("score"), st.get("risk", {}).get("flags"), "fit:", st.get("fit", {}).get("score"))
            if st.get("draft"):
                print("DRAFT:", st["draft"]["cover_letter"][:700])
                print("verification:", {k: v for k, v in st.get("verification", {}).items() if k != "checks"},
                      "critique:", st.get("critique"), "compliance:", st.get("compliance"))
            if r["status"] == "awaiting_approval" and "--approve" in sys.argv:
                r2 = await resume(g, u, r["thread_id"], {"action": "approve"})
                print("AFTER APPROVE:", r2["status"], r2.get("state", {}).get("submission"))
            print("usage:", sum(x.get("tokens_in", 0) + x.get("tokens_out", 0) for x in st.get("usage", [])), "tokens",
                  round(sum(x.get("cost_usd", 0) for x in st.get("usage", [])), 5), "USD", "errors:", st.get("errors"))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main([a for a in sys.argv[1:] if not a.startswith("--")]))
