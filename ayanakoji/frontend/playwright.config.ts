import { defineConfig, devices } from "@playwright/test";

const isCI = !!process.env.CI;

/**
 * E2E config. Playwright boots BOTH services itself: the FastAPI backend
 * (uv, ../backend) and the Next.js frontend — so `pnpm e2e` is self-contained
 * locally and in CI. The connection spec then asserts the real FE↔BE round-trip.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "uv run uvicorn app.main:app --port 8000",
      cwd: "../backend",
      url: "http://localhost:8000/health",
      reuseExistingServer: !isCI,
      timeout: 120_000,
      // Deterministic offline replies so the chat flow works without Azure creds.
      env: { OFFLINE_LLM: "true" },
    },
    {
      command: "pnpm dev --port 3000",
      url: "http://localhost:3000",
      reuseExistingServer: !isCI,
      timeout: 120_000,
      env: { NEXT_PUBLIC_API_BASE_URL: "http://localhost:8000" },
    },
  ],
});
