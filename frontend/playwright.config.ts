import { defineConfig } from "@playwright/test";

// End-to-end tests drive a real browser against the running local stack (docker compose up -d), never against Kalshi.
// Run from the host: E2E_EMAIL=... E2E_PASSWORD=... npm run test:e2e
export default defineConfig({
  testDir: "./e2e",
  workers: 1, // one shared test account and one shared database
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  reporter: [["list"]],
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000", headless: true, screenshot: "only-on-failure", trace: "retain-on-failure" },
});
