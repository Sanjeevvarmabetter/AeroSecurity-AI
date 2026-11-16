import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const VIEWER = process.env.E2E_API_TOKEN ?? "";
const ANALYST = process.env.E2E_ANALYST_TOKEN ?? "";
const ALLOW_AI = process.env.E2E_ALLOW_AI === "1";
const as = (page: Page, token: string) => page.addInitScript((t) => sessionStorage.setItem("aerosec.token", t), token);

test.describe("read-only", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!VIEWER, "set E2E_API_TOKEN");
    await as(page, VIEWER);
  });

  test("threat intelligence shows provenance and reliability limits for every document", async ({ page }) => {
    await page.goto("/threat-intel");
    await expect(page.getByRole("heading", { name: "Aviation Threat Intelligence" })).toBeVisible();
    const items = page.locator("li[id^=doc-]");
    await expect(items.first()).toBeVisible();
    const n = await items.count();
    expect(n).toBeGreaterThan(2);
    for (let i = 0; i < n; i++) {
      const it = items.nth(i);
      await expect(it).toContainText("Reliability limits:");
      await expect(it).toContainText("retrieved");
      await expect(it.locator("a[href^='https://']")).toHaveAttribute("rel", /noopener/);
    }
    await page.getByLabel("Search intelligence").fill("spoofing");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByText(/matching “spoofing”/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Import" })).toHaveCount(0); // viewers cannot import
    await page.screenshot({ path: "e2e/screenshots/threat-intel.png", fullPage: true });
  });

  test("assistant and reports are read-only for viewers and say what the assistant can and cannot do", async ({ page }) => {
    await page.goto("/assistant");
    await expect(page.getByText(/nine read-only platform tools/)).toBeVisible();
    await expect(page.getByText(/analyst-role token is required to chat/)).toBeVisible();
    await expect(page.getByLabel("Message")).toBeDisabled();
    await page.goto("/reports");
    await expect(page.getByText(/Select a report/)).toBeVisible();
  });
});

test("analyst: correlate with threat intel, report with provenance, PDF download, and a tool-using chat", async ({ page }) => {
  test.skip(!ANALYST || !ALLOW_AI, "set E2E_ANALYST_TOKEN and E2E_ALLOW_AI=1 (runs a real local model)");
  test.setTimeout(900_000);
  await as(page, ANALYST);

  // 1. open the real OS82 emergency
  await page.goto("/emergencies");
  await page.getByRole("row").filter({ hasText: "440604" }).getByRole("link", { name: "Details" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Squawk 7700");

  // 2. threat-intelligence correlation (real Ollama), layers visibly separated
  const corr = page.getByLabel("AI analysis").filter({ hasText: "Threat-intelligence correlation" });
  await corr.getByRole("button", { name: "Correlate with threat intel" }).click();
  await expect(corr.getByText("AI-GENERATED INTERPRETATION")).toBeVisible({ timeout: 360_000 });
  await expect(corr).toContainText("Four layers are kept separate");
  await expect(corr).toContainText("Documents supplied to the model");
  await expect(corr).toContainText("not evidence about this platform");
  await page.screenshot({ path: "e2e/screenshots/correlation.png", fullPage: true });

  // 3. plain AI explanation so the report can include AI content
  const expl = page.getByLabel("AI analysis").filter({ hasText: "AI explanation" });
  await expl.getByRole("button", { name: /Explain with AI|Regenerate/ }).click();
  await expect(expl.getByText("AI-GENERATED INTERPRETATION")).toBeVisible({ timeout: 360_000 });

  // 4. generate a report including AI; provenance must be labelled per section
  await page.getByLabel("Include existing AI analysis (labelled unverified)").check();
  await page.getByRole("button", { name: "Generate report" }).click();
  await expect(page).toHaveURL(/\/reports\/\d+/);
  await expect(page.getByText("UNREVIEWED.")).toBeVisible();
  await expect(page.getByText("VERIFIED PLATFORM DATA").first()).toBeVisible();
  await expect(page.getByText("AI-GENERATED · UNVERIFIED").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Executive summary" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Data limitations" })).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/report.png", fullPage: true });

  // 5. downloads are real files
  const [pdf] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download PDF" }).click()]);
  const pdfPath = await pdf.path();
  const head = readFileSync(pdfPath!).subarray(0, 5).toString();
  expect(head).toBe("%PDF-");
  expect(readFileSync(pdfPath!).length).toBeGreaterThan(2000);
  const [md] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download Markdown" }).click()]);
  const text = readFileSync((await md.path())!, "utf8");
  expect(text).toContain("UNREVIEWED");
  expect(text).toContain("AI-GENERATED, UNVERIFIED");

  // 6. the assistant answers from platform tools and cites records
  await page.goto("/assistant");
  await page.getByLabel("Message").fill("Summarize the emergency squawk events in the data. Which aircraft and what code?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("AI-GENERATED", { exact: true }).first()).toBeVisible({ timeout: 360_000 });
  await expect(page.getByText(/Used \d platform tools? \(read-only\)/)).toBeVisible();
  const cite = page.getByRole("link", { name: /^ANM-\d+$/ }).first();
  await expect(cite).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/assistant.png", fullPage: true });
  await cite.click();
  await expect(page).toHaveURL(/\/anomalies\/ANM-\d+/);
});
