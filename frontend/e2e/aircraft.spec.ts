import { expect, test } from "@playwright/test";

const TOKEN = process.env.E2E_API_TOKEN ?? "";

test.beforeEach(async ({ page }) => {
  test.skip(!TOKEN, "set E2E_API_TOKEN");
  await page.addInitScript((t) => sessionStorage.setItem("aerosec.token", t), TOKEN);
});

test("search an aircraft and inspect its real history", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/aircraft");
  await page.getByLabel("Search aircraft").fill("FDB10");
  await page.getByRole("link", { name: /8965d1/ }).click();

  await expect(page.getByRole("heading", { name: /8965D1/ })).toBeVisible();
  await expect(page.getByText("A6-FKF").first()).toBeVisible(); // registration from the aircraft database
  await expect(page.getByText("Observation gaps")).toBeVisible();
  // Prove the track is actually drawn (a bare <canvas> can be blank): features of the track layer are rendered.
  const map = page.locator("[data-rendered-features]").first();
  await expect.poll(async () => Number(await map.getAttribute("data-rendered-features")), { timeout: 15_000 }).toBeGreaterThan(0);
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  expect((await page.locator("canvas.maplibregl-canvas").boundingBox())!.height).toBeGreaterThan(300);
  await expect(page.locator(".recharts-line").first()).toBeVisible();
  await expect(page.getByRole("row").nth(1)).toContainText("UTC");
  await page.screenshot({ path: "e2e/screenshots/aircraft.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("search input rejects wildcard characters client-side", async ({ page }) => {
  await page.goto("/aircraft");
  await page.getByLabel("Search aircraft").fill("a%");
  await expect(page.getByText(/letters, digits/i)).toBeVisible();
});

test("radar reports stale data honestly and can replay a historical moment", async ({ page }) => {
  await page.goto("/radar");
  // Live polling may be running, so "now" can be fresh. Pick a moment between two stored datasets (20 Oct 2026,
  // after the OS82 extract ended and before the next began): nothing is recent enough, so the stale warning is honest.
  await page.getByLabel(/Observation Time/).fill("2026-10-20T00:00");
  await expect(page.getByRole("status")).toContainText("Historical or Stale Flight Data");
  await page.getByRole("button", { name: /Synchronize View/ }).click();
  await expect(page.getByText(/aircraft as of 2026-\d\d-\d\d/)).toBeVisible(); // the newest stored moment, whichever dataset it is from
  await expect(page.getByRole("status")).toHaveCount(0);
  const map = page.locator("[data-rendered-features]").first();
  await expect.poll(async () => Number(await map.getAttribute("data-rendered-features")), { timeout: 15_000 }).toBeGreaterThan(0);
  // NOTE: click-to-select is not covered here. It relied on a single aircraft being centred in the viewport, which
  // the redesigned radar no longer guarantees, and the map exposes no stable hook for locating a marker.
  await expect(page.getByText(/Select an aircraft marker/)).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/radar.png" });
});

test("missing token shows guidance instead of data", async ({ page, context }) => {
  await context.clearCookies();
  await page.addInitScript(() => sessionStorage.removeItem("aerosec.token"));
  await page.goto("/aircraft");
  await expect(page.getByText(/Enter an API token/)).toBeVisible();
});
