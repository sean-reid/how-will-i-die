import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";

const SHOTS = "/tmp/hwid-web";
mkdirSync(SHOTS, { recursive: true });

async function query(page, { country, age, sex }) {
  await page.goto("/");
  await expect(page.locator("#query")).toBeVisible();
  await page.selectOption("#country", country);
  await page.fill("#age", String(age));
  await page.selectOption("#sex", sex);
  await page.click('#query button[type="submit"]');
  await expect(page.locator("h2")).toContainText("Most likely eventual causes");
}

test("story a: grouped ranking renders with natural-frequency text", async ({ page }) => {
  await query(page, { country: "USA", age: 40, sex: "male" });
  const rows = page.locator("ol.ranking > li");
  await expect(rows).not.toHaveCount(0);
  const labels = await page.locator("ol.ranking .label").allTextContents();
  expect(labels.some((t) => t.includes("Cancer"))).toBeTruthy();
  await expect(page.locator("ol.ranking .freq").first()).toContainText("about 1 in");
  await page.screenshot({ path: `${SHOTS}/desktop-results.png`, fullPage: true });
});

test("story b: expanding a group reveals leaf causes and definitions", async ({ page }) => {
  await query(page, { country: "USA", age: 40, sex: "male" });
  const cancerRow = page
    .locator("ol.ranking > li")
    .filter({ has: page.locator(".label", { hasText: /^\d+\. Cancer$/ }) });
  const cancers = cancerRow.locator("button.row");
  await expect(cancers).toHaveAttribute("aria-expanded", "false");
  await cancers.click();
  await expect(cancers).toHaveAttribute("aria-expanded", "true");
  const leaves = cancerRow.locator("ul.leaves > li");
  await expect(leaves).not.toHaveCount(0);
  await expect(leaves.first().locator(".leaf-def")).not.toBeEmpty();
  await page.screenshot({ path: `${SHOTS}/desktop-expanded.png`, fullPage: true });
});

test("story c: icon array is present and labelled", async ({ page }) => {
  await query(page, { country: "USA", age: 40, sex: "male" });
  const icons = page.locator("svg.icons");
  await expect(icons).toBeVisible();
  await expect(icons).toHaveAttribute("aria-label", /1 in \d+/);
  expect(await icons.locator("circle.fig.on").count()).toBeGreaterThan(0);
});

test("story d: sensitive rows show a localized crisis line", async ({ page }) => {
  await query(page, { country: "USA", age: 20, sex: "male" });
  const selfHarm = page.locator("ol.ranking > li", { hasText: "Self-harm" });
  await expect(selfHarm).toHaveCount(1);
  await selfHarm.locator("button.row").click();
  await expect(selfHarm.locator(".crisis")).toContainText("988");
});

test("story e: mobile has no horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 720 });
  await query(page, { country: "GBR", age: 70, sex: "female" });
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: `${SHOTS}/mobile-results.png`, fullPage: true });
});

test("story f: about page loads", async ({ page }) => {
  await page.goto("/about.html");
  await expect(page.locator("h1")).toContainText("How this is calculated");
  await expect(page.locator("body")).toContainText("WHO Mortality Database");
});
