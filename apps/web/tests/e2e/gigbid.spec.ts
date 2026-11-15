import { expect, test, type Page, type Route } from "@playwright/test";

// The backend is mocked at the network layer so these UI tests are fast and deterministic.
// Graph resume/durability is covered by tests/integration/test_crash_resume.py against the real stack.

const me = { id: 1, email: "rev@gigbid.dev", name: "R", persona_id: "ai_ml", freelancer_id: "fl-1", marketplace: "gigsim", settings: {}, onboarded: true };
const job = { job_id: "dev-ai_ml-001", title: "MLOps platform setup for healthcare company", category: "ai_ml", status: "awaiting_approval", decision: "bid", fit: 1, risk: 0.1, risk_flags: [], price: 1500, connects: 8, budget: {}, stage: "drafted" };
const approval = {
  id: 7, status: "pending", thread_id: "bid:1:dev-ai_ml-001",
  payload: {
    job_title: job.title,
    draft: { cover_letter: "Your team needs reproducible releases. In my MLOps project the work cut release time from two weeks to one day [cs-ai_ml-mlops].", screening_answers: [], cited_ids: ["cs-ai_ml-mlops"] },
    evidence: { "cs-ai_ml-mlops": { id: "cs-ai_ml-mlops", title: "MLOps platform setup", type: "case_study", snippet: "cut model release time from two weeks to one day" } },
    claims: [{ claim: "cut release time [cs-ai_ml-mlops]", label: "supported", reason: "overlap 0.8" }],
    risk: { score: 0.1, flags: [] }, price: { amount: 1500, rationale: "60% into client range", connects_cost: 8 },
    critique: { score: 0.9, passed: true, issues: [] }, compliance: { passed: true, edits: [] },
    preview: { status: "dry_run", connects_cost: 8, connects_balance_after: 112 }, strategy: "evidence_first",
  },
};

async function mockApi(page: Page, opts: { onboarded?: boolean; marketplace?: boolean } = {}) {
  const resolved: unknown[] = [];
  let user = { ...me, onboarded: opts.onboarded ?? true };
  await page.route((u) => u.pathname.startsWith("/api/"), async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/api/auth/me") return json(user);
    if (p === "/api/auth/login") return json(user);
    if (p === "/api/onboarding") { user = { ...user, onboarded: true }; return json({ ok: true }); }
    if (p === "/api/health") return json({ api: true, marketplace: opts.marketplace ?? true, database: true, worker_queue: true, model_profile: "open", marketplace_adapter: "gigsim" });
    if (p === "/api/jobs") return json([job]);
    if (p === "/api/approvals") return json([{ id: 7, ref_id: job.job_id }]);
    if (p === `/api/jobs/${job.job_id}`) return json({ row: job, job: { description: "x", budget: {} }, analysis: {}, approval: { id: 7, status: "pending" }, runs: [] });
    if (p === "/api/approvals/7") return json(approval);
    if (p === "/api/approvals/7/resolve") { resolved.push(route.request().postDataJSON()); return json({ queued: true }); }
    return json({});
  });
  return resolved;
}

test("onboarding: a new user sets a profile and lands in the inbox", async ({ page }) => {
  await mockApi(page, { onboarded: false });
  await page.goto("/onboarding");
  await page.getByLabel("Profile").selectOption("data_analyst");
  await page.getByLabel("Weekly Connects budget").fill("60");
  await page.getByRole("button", { name: "Start finding jobs" }).click();
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
});

test("approving a proposal sends an approve decision and shows evidence on hover", async ({ page }) => {
  const resolved = await mockApi(page);
  await page.goto(`/studio/${job.job_id}`);
  const cite = page.getByLabel("evidence cs-ai_ml-mlops").first();
  await cite.hover();
  await expect(page.getByRole("tooltip").first()).toContainText("two weeks to one day");
  await expect(page.getByTestId("dry-run")).toContainText("Connects cost 8");
  await page.getByRole("button", { name: "Approve and submit" }).click();
  await expect.poll(() => resolved.length).toBe(1);
  expect(resolved[0]).toEqual({ action: "approve" });
});

test("rejecting requires a reason and sends it", async ({ page }) => {
  const resolved = await mockApi(page);
  await page.goto(`/studio/${job.job_id}`);
  await page.getByRole("button", { name: "Reject" }).click();
  await expect(page.getByRole("status")).toContainText("Give a reason");
  expect(resolved.length).toBe(0);
  await page.getByLabel("Reason (required to reject)").fill("Budget too low for this scope");
  await page.getByRole("button", { name: "Reject" }).click();
  await expect.poll(() => resolved.length).toBe(1);
  expect(resolved[0]).toEqual({ action: "reject", reason: "Budget too low for this scope" });
});

test("editing a draft sends the edited text for compliance re-check", async ({ page }) => {
  const resolved = await mockApi(page);
  await page.goto(`/studio/${job.job_id}`);
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  const editor = page.getByTestId("draft-editor");
  await editor.fill("Your team needs reproducible releases, and I have done this before [cs-ai_ml-mlops].");
  await expect(page.getByText("You edited the draft")).toBeVisible();
  await page.getByRole("button", { name: "Approve with my edits" }).click();
  await expect.poll(() => resolved.length).toBe(1);
  expect((resolved[0] as { action: string }).action).toBe("edit");
  expect((resolved[0] as { text: string }).text).toContain("I have done this before");
});

test("degraded mode: the UI says when the marketplace is unavailable", async ({ page }) => {
  await mockApi(page, { marketplace: false });
  await page.goto("/");
  await expect(page.getByTestId("degraded-banner")).toContainText("Marketplace unavailable");
  await expect(page.getByTestId("inbox-table")).toBeVisible();
});
