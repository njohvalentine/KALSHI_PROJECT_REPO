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
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/approval");
  await expect(page).toHaveURL(/\/login/);
});
