import { expect, test } from "@playwright/test";

test("landing page reaches the live backend", async ({ page }) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "Ayanakoji" }),
  ).toBeVisible();

  // The status component pings /api/ping on mount; assert the real round-trip.
  await expect(page.getByText("Backend connected")).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText("ayanakoji-backend")).toBeVisible();
});
