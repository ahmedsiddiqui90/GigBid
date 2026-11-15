// Capture README screenshots from the running app (API on :8000 serving, Vite on :5173).
// Usage: REVIEWER_PASSWORD=... node scripts/screens.mjs
import { chromium } from "@playwright/test";

const base = process.env.BASE_URL ?? "http://localhost:5173";
const out = process.env.OUT ?? "../../docs/images";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto(`${base}/login`);
await page.getByLabel("Email").fill(process.env.REVIEWER_EMAIL ?? "reviewer@gigbid.dev");
await page.getByLabel("Password").fill(process.env.REVIEWER_PASSWORD ?? "");
await page.getByRole("button", { name: "Sign in" }).click();
await page.getByRole("heading", { name: "Job inbox" }).waitFor();
await page.waitForTimeout(800);
await page.screenshot({ path: `${out}/01-inbox.png` });
const review = page.getByRole("link", { name: "Review" }).first();
const href = await review.getAttribute("href");
const jobId = href.split("/").pop();
await page.goto(`${base}/jobs/${jobId}`);
await page.getByText("Requirement to evidence matrix").waitFor();
await page.waitForTimeout(500);
await page.screenshot({ path: `${out}/02-job-detail.png`, fullPage: false });
await page.goto(`${base}/studio/${jobId}`);
await page.getByText("Proposal studio").waitFor();
await page.locator(".cite").first().hover();
await page.waitForTimeout(400);
await page.screenshot({ path: `${out}/03-studio-evidence.png` });
await page.locator("[data-testid=dry-run]").scrollIntoViewIfNeeded();
await page.screenshot({ path: `${out}/04-studio-dry-run.png` });
const skipped = page.getByRole("button", { name: "skip" });
await page.goto(`${base}/`);
await page.getByRole("button", { name: "skip", exact: true }).click();
await page.waitForTimeout(500);
await page.screenshot({ path: `${out}/05-skipped-scams.png` });
for (const p of ["pipeline", "analytics", "settings"]) {
  await page.goto(`${base}/${p}`);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${out}/06-${p}.png` });
}
void skipped;
await browser.close();
console.log("screens saved to", out);
