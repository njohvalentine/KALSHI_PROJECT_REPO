import { ADD_BUTTON, expect, runsWithButtons, test } from "./fixtures";

const panel = (page: import("@playwright/test").Page) => page.getByRole("region", { name: "Ticket" });

test("legs from two runs stay on the ticket while moving between pages, and can be removed", async ({ signedIn: page }) => {
  const runs = await runsWithButtons(page, 2);
  test.skip(runs.length < 2, "fewer than two finished runs with priced markets");
  await page.goto(runs[0]);
  await page.getByRole("button", { name: ADD_BUTTON }).first().click();
  await expect(panel(page)).toContainText("Ticket: 1 leg");
  await page.goto(runs[1]); // a full page load: the legs come back from the browser's session storage
  await expect(panel(page)).toContainText("Ticket: 1 leg");
  await page.getByRole("button", { name: ADD_BUTTON }).first().click();
  await expect(panel(page)).toContainText("Ticket: 2 legs");
  await expect(panel(page)).toContainText("Together: price");
  await expect(panel(page)).not.toContainText("several bets on this ticket"); // two games: nothing is linked
  for (let left = 2; left > 0; left--) await panel(page).getByRole("button", { name: "Remove" }).first().click();
  await expect(panel(page)).toHaveCount(0);
});

test("two markets of one game make the combined numbers rough, and a second market of the same group replaces the first", async ({ signedIn: page }) => {
  // a run with more than one kind of market (winner plus total, both teams to score or spread)
  const runs = await runsWithButtons(page, 8, 8);
  let found = false;
  for (const href of runs) {
    await page.goto(href);
    if ((await page.locator('section[aria-labelledby="prediction-heading"] h3').count()) >= 2) { // one heading per kind of market
      found = true;
      break;
    }
  }
  test.skip(!found, "no finished run with more than one kind of market");
  const add = page.getByRole("button", { name: ADD_BUTTON });
  await add.first().click(); // the first group (the winner)
  await add.last().click(); // the last group (another kind of market)
  await expect(panel(page)).toContainText("Ticket: 2 legs");
  await expect(panel(page)).toContainText("several bets on this ticket");
  // another button of the first group replaces the first leg: still two legs
  await page.getByRole("button", { name: ADD_BUTTON }).nth(1).click();
  await expect(panel(page)).toContainText("Ticket: 2 legs");
});

test("a prepared ticket waits on the Approval page with its checks and is rejected", async ({ signedIn: page }) => {
  const runs = await runsWithButtons(page, 6, 10);
  test.skip(runs.length === 0, "no finished run with priced markets");
  let orderId: number | null = null;
  try {
    let refused = "";
    for (const href of runs) {
      await page.goto(href);
      await page.getByRole("button", { name: ADD_BUTTON }).first().click();
      const response = page.waitForResponse((r) => r.url().endsWith("/api/orders") && r.request().method() === "POST");
      await panel(page).getByRole("button", { name: "Prepare ticket" }).click();
      const done = await response;
      if (done.status() === 201) {
        orderId = (await done.json()).id;
        break;
      }
      const body = await done.json().catch(() => ({}));
      refused = typeof body.detail === "string" ? body.detail : (body.detail?.message ?? `HTTP ${done.status()}`);
      await panel(page).getByRole("button", { name: "Remove" }).first().click();
    }
    test.skip(orderId === null, `no game is open for a ticket right now (last answer: ${refused})`);
    await expect(page).toHaveURL(/\/approval/);
    const waiting = page.locator('section[aria-labelledby="waiting-heading"] li.rounded-xl');
    const before = await waiting.count();
    await expect(page.getByRole("list", { name: "Checks" }).first()).toBeVisible();
    await page.getByRole("button", { name: "Reject" }).first().click();
    await page.getByRole("button", { name: "Confirm reject" }).click();
    await expect(waiting).toHaveCount(before - 1);
    orderId = null; // rejected: nothing to clean up
  } finally {
    // a failure must not leave an open ticket behind
    if (orderId !== null) await page.request.post(`/api/orders/${orderId}/reject`, { headers: { "X-Requested-With": "e2e" }, data: { reason: "e2e cleanup" } });
  }
});

test("the Results page loads", async ({ signedIn: page }) => {
  await page.goto("/results");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Results");
});
