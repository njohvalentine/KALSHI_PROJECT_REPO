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
  // the kinds of market after the first are folded: open them, as a person would
  const closed = page.locator('section[aria-labelledby="prediction-heading"] details:not([open]) > summary');
  for (let n = await closed.count(); n > 0; n--) await closed.first().click();
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
  for (const label of ["Simulated orders settled", "Chosen side at the ask", "Flagged bets"]) await expect(page.getByText(label, { exact: true })).toBeVisible();
});

test("any researched game with a fresh forecast can be added from the Opportunities page, and the ticket says when it is not marked worth a look", async ({ signedIn: page }) => {
  await page.goto("/opportunities?all=1");
  await page.getByText(/researched games? that have not started/).waitFor();
  const notFlagged = page.locator("tr", { hasText: "NO BET" }).filter({ has: page.getByRole("button", { name: ADD_BUTTON }) });
  test.skip((await notFlagged.count()) === 0, "no row that is not flagged and has a fresh forecast (forecasts older than 12 hours cannot be added)");
  await notFlagged.first().getByRole("button", { name: ADD_BUTTON }).click();
  await expect(page.getByRole("region", { name: "Ticket" })).toContainText("not marked worth a look");
  await page.getByRole("region", { name: "Ticket" }).getByRole("button", { name: "Remove" }).first().click();
});

test("a row with an old forecast says to research the game again and has no add button", async ({ signedIn: page }) => {
  await page.goto("/opportunities?all=1");
  await page.getByText(/researched games? that have not started/).waitFor();
  const stale = page.locator("tr", { hasText: "Forecast is old" });
  test.skip((await stale.count()) === 0, "no row with an old forecast right now");
  await expect(stale.first()).toContainText("research the game again");
  await expect(stale.first().getByRole("button", { name: ADD_BUTTON })).toHaveCount(0);
});

test("the Games page offers more sports found on Kalshi, marks them as not yet measured, and keeps the measured ones as before", async ({ signedIn: page }) => {
  await page.goto("/games");
  await expect(page.getByRole("navigation", { name: "Sport", exact: true })).toBeVisible();
  const more = page.getByRole("navigation", { name: "More sports on Kalshi" });
  test.skip((await more.count()) === 0, "no other sport found on Kalshi right now (or Kalshi could not be reached)");
  const unmeasured = more.getByRole("link").filter({ hasNotText: "other leagues" }); // a sport that is not one of the measured ones
  test.skip((await unmeasured.count()) === 0, "no sport beyond the measured ones is offered right now");
  await unmeasured.first().click();
  await expect(page).toHaveURL(/more=1/);
  await expect(page.getByText("Not yet measured", { exact: true }).first()).toBeVisible({ timeout: 60_000 }); // the first load asks Kalshi about each series
});

test("the Dashboard shows the message about the scores, the cards and the charts", async ({ signedIn: page }) => {
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Dashboard");
  await expect(page.getByRole("status").filter({ hasText: /finished|edge|ahead/ })).toBeVisible();
  for (const label of ["Finished games scored", "Worth a look today", "Flagged bets so far", "Research spend"]) await expect(page.getByText(label, { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Forecast error, all games" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "By sport" })).toBeVisible();
});

test("a finished run opens with an At a glance box, and the evidence is folded until it is opened", async ({ signedIn: page }) => {
  await page.goto("/prediction");
  const done = page.locator("tr", { hasText: "Done" });
  test.skip((await done.count()) === 0, "no finished run yet");
  await done.first().getByRole("link").first().click();
  await expect(page.getByRole("heading", { name: "At a glance" })).toBeVisible();
  await expect(page.getByText(/^(NO BET|Worth a look)/).first()).toBeVisible(); // the verdict is the headline of the box
  const text = page.getByText("“Supported” means the page itself says it");
  await expect(text).toBeHidden(); // folded
  await page.getByRole("heading", { name: "The evidence" }).click();
  await expect(text).toBeVisible();
});

test("Research on a game with a fresh forecast asks first, and confirming sends confirm_repeat", async ({ signedIn: page }) => {
  const sent: unknown[] = [];
  await page.route("**/api/runs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const body = route.request().postDataJSON();
    sent.push(body);
    if (!body.confirm_repeat) {
      return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ code: "recently_researched", run_id: null, detail: "This game was researched 3 hours ago for $0.43, and its forecast is still fresh." }) });
    }
    return route.fulfill({ status: 429, contentType: "application/json", body: JSON.stringify({ detail: "stopped here by the test" }) }); // no real run, no spend
  });
  await page.goto("/games");
  await page.getByRole("button", { name: /^Research/ }).first().click();
  await expect(page.getByRole("alertdialog", { name: "Research again?" })).toContainText("researched 3 hours ago for $0.43");
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await page.getByRole("button", { name: /^Research/ }).first().click();
  await page.getByRole("button", { name: "Research again anyway" }).click();
  await expect(page.getByText("stopped here by the test")).toBeVisible();
  expect(sent).toEqual([
    { event_ticker: expect.any(String), confirm_repeat: false },
    { event_ticker: expect.any(String), confirm_repeat: false },
    { event_ticker: expect.any(String), confirm_repeat: true },
  ]);
});

test("the free bookmaker check is a button that sends a POST: nothing runs on load or from the address, and the labels appear after the press", async ({ signedIn: page }) => {
  const calls: string[] = [];
  await page.route("**/api/games/screen**", async (route) => {
    calls.push(route.request().method());
    return route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ results: {}, notes: ["a note from the test"], credits: { remaining: 400, used: 3 } }),
    });
  });
  await page.goto("/games?screen=1"); // an old-style address: it must not run anything
  const button = page.getByRole("button", { name: "Check these games against the bookmakers" });
  await expect(button).toBeVisible(); // needs the odds feed on (ODDS_ENABLED)
  await expect(page.getByText("Checked against the bookmakers")).toHaveCount(0);
  expect(calls).toEqual([]);
  await button.click();
  await expect(page.getByText(/Checked against the bookmakers: 3 odds credits used, 400 left this month/)).toBeVisible();
  await expect(page.getByText("a note from the test")).toBeVisible();
  expect(calls).toEqual(["POST"]); // the browser sent a POST, once
});
