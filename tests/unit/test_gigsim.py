import os

os.environ["GIGSIM_ERROR_RATE"] = "0"
os.environ["GIGSIM_STATE"] = os.path.join(os.path.dirname(__file__), "_gigsim_state_test.json")

from fastapi.testclient import TestClient  # noqa: E402

from gigsim.app import app  # noqa: E402

H = {"Authorization": "Bearer gigsim-dev-token"}
c = TestClient(app)


def test_auth_required():
    assert c.get("/jobs").status_code == 401


def test_search_and_connects_cost():
    c.post("/admin/reset")
    r = c.get("/jobs", headers=H, params={"q": "dashboard"}).json()
    assert r["total"] > 0 and "connects_cost" in r["jobs"][0]
    assert "target_persona" not in r["jobs"][0]


def test_idempotent_submit_spends_once():
    c.post("/admin/reset")
    job = c.get("/jobs/dev-ai_ml-001", headers=H).json()
    body = {"freelancer_id": "f1", "job_id": job["job_id"], "cover_letter": "x " * 30, "bid_amount": 500, "submit": True}
    a = c.post("/proposals", json=body, headers={**H, "Idempotency-Key": "k1"}).json()
    b = c.post("/proposals", json=body, headers={**H, "Idempotency-Key": "k1"}).json()
    assert a["proposal_id"] == b["proposal_id"] and b["idempotent_replay"]
    bal = c.get("/freelancers/f1/connects", headers=H).json()["balance"]
    assert bal == 120 - job["connects_cost"]


def test_writes_need_idempotency_key():
    r = c.post("/proposals", json={"freelancer_id": "f", "job_id": "dev-ai_ml-001", "cover_letter": "x" * 30,
                                   "bid_amount": 1}, headers=H)
    assert r.status_code == 400
