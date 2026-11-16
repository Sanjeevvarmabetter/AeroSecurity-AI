/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": process.env.API_TARGET ?? "http://localhost:8000" } },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test-setup.ts"], exclude: ["e2e/**", "node_modules/**"] },
});
