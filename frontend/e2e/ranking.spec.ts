import { expect, test } from "./fixtures";

test("the market filter on the Ranking page uses plain labels, not internal names", async ({ signedIn: page }) => {
  await page.goto("/ranking");
  const filter = page.locator("div", { hasText: /^Market:/ }).last();
  const buttons = await filter.getByRole("link").allTextContents();
  test.skip(buttons.length < 2, "no researched game that has not started: the filter is not shown");
  for (const label of buttons) expect(label).not.toMatch(/^[a-z0-9]+(_[a-z0-9]+)*$/); // btts, winner, h1_total ... are internal names
});
