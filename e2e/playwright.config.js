/**
 * Playwright configuration for the Cusin Gallery end-to-end suite (Part R3).
 *
 * This suite is INTENTIONALLY NOT part of `npm test` (vitest). It drives a
 * real browser against a fully running stack -- the Django backend AND the
 * built/served frontend -- so it needs both up first. See docs/E2E.md for
 * the exact bring-up commands.
 *
 * Point it at your running app with E2E_BASE_URL (defaults to the Vite dev
 * server). When the backend is same-origin (recommended), no extra env is
 * needed; the frontend proxies /api to the backend in dev.
 */
const { defineConfig, devices } = require("@playwright/test");

const BASE_URL = process.env.E2E_BASE_URL || "http://localhost:5173";

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: /.*\.spec\.js$/,
  // Real flows hit a real DB; give them room but never hang forever.
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false, // flows share seeded data / cart state
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "fa-IR",
    timezoneId: "Asia/Tehran",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
  ],
});
