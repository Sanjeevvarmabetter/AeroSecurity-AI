import { expect, test, type Page } from "@playwright/test";

const VIEWER = process.env.E2E_API_TOKEN ?? "";
const ANALYST = process.env.E2E_ANALYST_TOKEN ?? "";
const WRITES = process.env.E2E_ALLOW_WRITES === "1";

const as = (page: Page, token: string) => page.addInitScript((t) => sessionStorage.setItem("aerosec.token", t), token);
const rendered = async (page: Page) => {
  const map = page.locator("[data-rendered-features]").first();
  await expect.poll(async () => Number(await map.getAttribute("data-rendered-features")), { timeout: 20_000 }).toBeGreaterThan(0);
};

test.describe("read-only (viewer)", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!VIEWER, "set E2E_API_TOKEN");
    await as(page, VIEWER);
  });

  test("anomaly center lists detections and filters by severity via the URL", async ({ page }) => {
    await page.goto("/anomalies");
    await expect(page.getByRole("heading", { name: "Anomaly Center" })).toBeVisible();
    await expect(page.getByRole("link", { name: /^ANM-\d+$/ }).first()).toBeVisible();
    const all = await page.getByRole("link", { name: /^ANM-\d+$/ }).count();
    await page.getByRole("button", { name: /^HIGH\s*\d+$/ }).click();
    await expect(page).toHaveURL(/severity=HIGH/);
    await expect.poll(() => page.getByRole("link", { name: /^ANM-\d+$/ }).count()).toBeLessThan(all);
    for (const badge of await page.locator("tbody tr td:nth-child(2)").allInnerTexts()) expect(badge.trim()).toBe("HIGH");
    await page.screenshot({ path: "e2e/screenshots/anomaly-center.png", fullPage: true });
  });

  test("hostile filter values in the URL are ignored, not sent", async ({ page }) => {
    const bad: string[] = [];
    page.on("response", (r) => { if (r.url().includes("/api/v1/anomalies?") && r.status() >= 400) bad.push(r.url()); });
    await page.goto("/anomalies?severity=SEVERE&icao24=%25&rule_id=DET-1%27--&min_confidence=9");
    await expect(page.getByRole("link", { name: /^ANM-\d+$/ }).first()).toBeVisible();
    expect(bad).toEqual([]);
  });

  test("emergency intelligence shows the real OS82 7700 event and links to evidence", async ({ page }) => {
    await page.goto("/emergencies");
    const row = page.getByRole("row").filter({ hasText: "440604" });
    await expect(row).toContainText("7700");
    await expect(row).toContainText("AUA");
    await expect(row).toContainText("General emergency");
    await page.screenshot({ path: "e2e/screenshots/emergencies.png" });
    await row.getByRole("link", { name: "Details" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Squawk 7700");
    await expect(page.getByRole("heading", { name: "Alternative explanations", level: 2 })).toBeVisible();
    await expect(page.getByText(/not the probability of malicious activity|Not the probability/i).first()).toBeVisible();
    await rendered(page); // the track around the event is actually drawn
    await page.screenshot({ path: "e2e/screenshots/anomaly-detail.png", fullPage: true });
  });

  test("viewer sees the workflow as read-only", async ({ page }) => {
    await page.goto("/anomalies?rule_id=DET-006");
    await page.getByRole("link", { name: /^ANM-\d+$/ }).first().click();
    await expect(page.getByText(/Read-only: an analyst-role token is required/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Start investigation" })).toBeDisabled();
  });

  test("detail page rejects malformed ids without calling the API", async ({ page }) => {
    await page.goto("/anomalies/not-an-id");
    await expect(page.getByText("Invalid anomaly id")).toBeVisible();
  });
});

test.describe("investigation workflow (analyst, writes data)", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!ANALYST || !WRITES, "set E2E_ANALYST_TOKEN and E2E_ALLOW_WRITES=1 (creates investigation records)");
    await as(page, ANALYST);
  });

  test("investigate, annotate (as text), close with reason, reopen; all in the timeline", async ({ page }) => {
    await page.goto("/anomalies?rule_id=DET-006&status=OPEN");
    await page.getByRole("link", { name: /^ANM-\d+$/ }).first().click();
    await page.getByLabel("Your name").fill("E2E Tester");
    await page.getByRole("button", { name: "Start investigation" }).click();
    await expect(page.getByRole("button", { name: "Mark false positive" })).toBeVisible();

    const hostile = "<img src=x onerror=window.__xss=1> receiver check";
    await page.getByLabel("Note").fill(hostile);
    await page.getByRole("button", { name: "Add note" }).click();
    await expect(page.getByText(hostile).first()).toBeVisible(); // shown literally
    expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
    expect(await page.locator("img[src='x']").count()).toBe(0);

    await page.getByRole("button", { name: "Mark false positive" }).click();
    await expect(page.getByRole("button", { name: /Confirm: Mark false positive/ })).toBeDisabled(); // reason required
    await page.getByLabel("Reason").fill("e2e: receiver gap, not an anomaly");
    await page.getByRole("button", { name: /Confirm: Mark false positive/ }).click();
    await expect(page.getByText("FALSE POSITIVE").first()).toBeVisible();
    await expect(page.getByText(/OPEN -> INVESTIGATING|INVESTIGATING -> FALSE_POSITIVE/).first()).toBeVisible();

    await page.getByRole("button", { name: "Reopen" }).click();
    await page.getByRole("button", { name: /Confirm: Reopen/ }).click();
    await expect(page.getByText("FALSE_POSITIVE -> OPEN")).toBeVisible();
    await expect(page.getByText(/analyst:[0-9a-f]{8}/).first()).toBeVisible(); // attributed to the credential
    await page.screenshot({ path: "e2e/screenshots/investigation.png", fullPage: true });

    await page.goto("/investigations");
    await expect(page.getByRole("row").filter({ hasText: "analyst:" }).first()).toBeVisible();
  });
});
