import { expect, test, type Page } from "@playwright/test";

const VIEWER = process.env.E2E_API_TOKEN ?? "";
const ANALYST = process.env.E2E_ANALYST_TOKEN ?? "";
const ALLOW_AI = process.env.E2E_ALLOW_AI === "1";
const as = (page: Page, token: string) => page.addInitScript((t) => sessionStorage.setItem("aerosec.token", t), token);

async function openEmergency(page: Page) {
  await page.goto("/emergencies");
  await page.getByRole("row").filter({ hasText: "440604" }).getByRole("link", { name: "Details" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Squawk 7700");
}

test.describe("read-only", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!VIEWER, "set E2E_API_TOKEN");
    await as(page, VIEWER);
  });

  test("AI panel is visible but disabled for viewers and states what the AI may not do", async ({ page }) => {
    await openEmergency(page);
    const panel = page.getByLabel("AI analysis").filter({ hasText: "AI explanation" }).first();
    await expect(panel).toContainText("never changes a detection, severity or status");
    await expect(panel).toContainText("analyst-role token is required");
    await expect(panel.getByRole("button", { name: /Explain with AI|Regenerate/ })).toBeDisabled();
  });

  test("AI configuration shows both providers, health and where data goes; read-only for viewers", async ({ page }) => {
    await page.goto("/ai-config");
    await expect(page.getByRole("heading", { name: "AI Configuration" })).toBeVisible();
    await expect(page.getByText("Ollama (local)")).toBeVisible();
    await expect(page.getByText("OpenRouter (cloud)")).toBeVisible();
    await expect(page.getByText(/Prompts and data stay on this machine/)).toBeVisible();
    await expect(page.getByText(/sent to OpenRouter/)).toBeVisible();
    await expect(page.getByText(/needs an admin-role token/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Use as default" })).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText("sk-or-"); // no key ever reaches the browser
    await page.screenshot({ path: "e2e/screenshots/ai-config.png", fullPage: true });
  });
});

test("analyst generates a grounded explanation with the local model (real Ollama)", async ({ page }) => {
  test.skip(!ANALYST || !ALLOW_AI, "set E2E_ANALYST_TOKEN and E2E_ALLOW_AI=1 (runs a real model)");
  test.setTimeout(400_000);
  await as(page, ANALYST);
  await openEmergency(page);
  const panel = page.getByLabel("AI analysis");
  await panel.getByLabel("AI provider").selectOption("ollama");
  await panel.getByRole("button", { name: /Explain with AI|Regenerate/ }).click();
  await expect(panel.getByRole("button", { name: /Generating/ })).toBeVisible();
  await expect(panel.getByText("AI-GENERATED INTERPRETATION")).toBeVisible({ timeout: 360_000 });
  await expect(panel).toContainText("not a verified finding");
  await expect(panel).toContainText("Deterministic detection (unchanged by AI)");
  await expect(panel).toContainText("DET-005 v1.0.0 · HIGH");
  await expect(panel).toContainText("Alternative explanations");
  await expect(panel).toContainText("ollama ·");
  // citations are real: clicking an E-ref highlights the matching evidence row
  const chip = panel.getByRole("button", { name: /^E\d+$/ }).first();
  await expect(chip).toBeVisible();
  const ref = (await chip.innerText()).trim();
  await chip.click();
  await expect(page.locator(`#ev-${ref.slice(1)}`)).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/ai-explanation.png", fullPage: true });
});
