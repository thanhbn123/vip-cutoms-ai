import { defineConfig } from "@playwright/test";

// Browser smoke against the real stack. scripts/e2e.sh boots PostgreSQL (test DB), API and Vite before running this.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    headless: true,
    // Pre-installed browser (cloud session) or any Chromium: PW_CHROMIUM_PATH=/path/to/chrome. Unset → Playwright's own download.
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  reporter: [["list"]],
});
