import { defineConfig } from "@playwright/test";

// Runs against a live stack (docker compose up). E2E_API_TOKEN must be a viewer-or-higher token.
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080", viewport: { width: 1400, height: 900 } },
  reporter: [["list"]],
});
