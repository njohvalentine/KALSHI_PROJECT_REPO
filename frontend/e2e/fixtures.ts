import { expect, test as base, type Page } from "@playwright/test";

/** The test account comes from the environment: there is no default and no password in the repository. */
export function credentials(): { email: string; password: string } {
  const email = process.env.E2E_EMAIL;
  const password = process.env.E2E_PASSWORD;
  if (!email || !password) throw new Error("Set E2E_EMAIL and E2E_PASSWORD to the test account (see docs/RUNBOOK.md, tests section).");
  return { email, password };
}

export async function signIn(page: Page, password?: string) {
  const { email, password: right } = credentials();
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password ?? right);
  await page.getByRole("button", { name: "Sign in" }).click();
}

export const ADD_BUTTON = /^Add “(yes|no)” at \d+¢/;

export const test = base.extend<{ signedIn: Page }>({
  signedIn: async ({ page }, provide) => {
    await signIn(page);
    await expect(page).toHaveURL(/\/games/);
    await provide(page); // (named provide, not use: a function named use looks like a React hook to the linter)
  },
});

export { expect };

/** Links of the runs on the Prediction page, newest first. */
export async function runLinks(page: Page): Promise<string[]> {
  await page.goto("/prediction");
  const hrefs = await page.locator('a[href^="/prediction/"]').evaluateAll((links) => links.map((a) => (a as HTMLAnchorElement).getAttribute("href") ?? ""));
  return [...new Set(hrefs)];
}

/** The first run pages that have at least `count` add-to-ticket buttons (a finished run with priced markets). */
export async function runsWithButtons(page: Page, wanted: number, look = 8): Promise<string[]> {
  const found: string[] = [];
  for (const href of (await runLinks(page)).slice(0, look)) {
    await page.goto(href);
    await page.getByRole("heading", { level: 1 }).first().waitFor();
    if ((await page.getByRole("button", { name: ADD_BUTTON }).count()) > 0) found.push(href);
    if (found.length >= wanted) break;
  }
  return found;
}
