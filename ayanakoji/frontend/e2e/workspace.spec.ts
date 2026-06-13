import { expect, test } from "@playwright/test";

/**
 * Critical learner journey, end to end against both live services (backend runs
 * in OFFLINE_LLM mode so replies are deterministic): sign in by choosing a
 * persona, start a course by sending a message, see the reply stream and the
 * record get created, visit assessments, and sign out.
 */
test("learner signs in, starts a course, views assessments, and signs out", async ({
  page,
}) => {
  await page.goto("/");

  // The entry point routes to the account chooser.
  await expect(
    page.getByRole("heading", { name: "Sign in to your account" }),
  ).toBeVisible({ timeout: 15_000 });

  // Choosing a learner is the sign-in.
  await page.getByRole("button", { name: /Sign in as Vega/ }).click();

  // Lands in the workspace on a brand-new chat (no page switcher yet).
  const composer = page.getByRole("textbox", { name: "Message" });
  await expect(composer).toBeVisible();
  await expect(page.getByRole("tab", { name: "Assessments" })).toHaveCount(0);

  // First message creates the course and streams the reply.
  await composer.fill("How do Azure Functions triggers and bindings work end to end?");
  await composer.press("Enter");

  await expect(page).toHaveURL(/\/chat\/[0-9a-f]{16,}$/, { timeout: 15_000 });
  await expect(page.getByText(/offline mode/i)).toBeVisible({ timeout: 15_000 });

  // The page switcher now exists; assessments shows its empty state.
  await page.getByRole("tab", { name: "Assessments" }).click();
  await expect(page.getByText("No assessments yet")).toBeVisible();

  // Back to chat: the conversation was persisted and reloads from the backend.
  await page.getByRole("tab", { name: "Chat" }).click();
  await expect(page.getByText(/offline mode/i)).toBeVisible({ timeout: 15_000 });

  // Sign out returns to the chooser.
  await page.getByRole("button", { name: /sign out/i }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in to your account" }),
  ).toBeVisible();
});
