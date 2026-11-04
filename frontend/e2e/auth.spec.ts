import { expect, test as plain } from "@playwright/test";
import { credentials, signIn, test } from "./fixtures";

plain("a page behind the sign-in redirects to it", async ({ page }) => {
  await page.goto("/approval");
  await expect(page).toHaveURL(/\/login/);
});

plain("a wrong password shows the message and stays on the sign-in page", async ({ page }) => {
  credentials(); // fails early with a clear message if the account is not set
  await signIn(page, "not the password at all");
  await expect(page.getByRole("alert").filter({ hasText: "Invalid email or password" })).toBeVisible(); // Next.js also has an empty alert for route changes
  await expect(page).toHaveURL(/\/login/);
});

test("signing in reaches the Games page and signing out returns to the sign-in page", async ({ signedIn: page }) => {
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  await expect(page.getByText("Paper trading")).toBeVisible(); // the chip that replaced the orange bar
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/approval");
  await expect(page).toHaveURL(/\/login/);
});

plain("a session cookie the backend does not accept ends on the sign-in form, not in a redirect loop", async ({ page, context }) => {
  await context.addCookies([{ name: "session", value: "not-a-real-session", url: "http://127.0.0.1:3000" }]);
  await page.goto("/games"); // the page gets a 401 from the backend and sends the person to the sign-in page
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await page.goto("/login"); // opening the sign-in page directly with the same stale cookie must also show the form
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("a signed-in person who opens the sign-in page lands in the app", async ({ signedIn: page }) => {
  await page.goto("/login");
  await expect(page).toHaveURL(/\/games/);
});
