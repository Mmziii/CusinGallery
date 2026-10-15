/*
 * Readiness card fit: «آمادگی راه‌اندازی» at the widths Windows reports.
 *
 * The bug this guards: the missing-items list («تلفن و نشانی فروشگاه»,
 * «صفحه‌های حقوقی/اعتماد») was laid out as 240px tracks that started at
 * x = -57 -- outside the viewport, on the page's left (start) edge in RTL.
 * The dashboard then grew a horizontal scrollbar (70px at 1280, 57px at
 * 1366, 31px at 1536) that pushed the sidebar off screen, and the clipped
 * rows read «متن این ص…».
 *
 * Two causes, both pinned here:
 *   1. a wrapped {# … #} comment inside the row leaked into the page as
 *      text, and as an anonymous flex item it took a share of the row's
 *      width -- leaving the sub-list less than its own 15rem minimum;
 *   2. minmax(15rem, 1fr) floors a track at 240px even when the row is
 *      narrower, and no flex/grid child was allowed to shrink (min-width).
 *
 * What is checked on /admin/, at 1280 / 1366 / 1536:
 *   1. the document never scrolls sideways;
 *   2. every .cusin-readiness-missing li is fully inside the viewport;
 *   3. no readiness text is clipped by its own box;
 *   4. the readiness rows are full-width blocks (one row of the card is
 *      as wide as the card, not a narrow column beside an icon).
 *
 * Requires a running stack and an admin account:
 *   E2E_BASE_URL, E2E_ADMIN_USER, E2E_ADMIN_PASSWORD
 *
 * Run with: npx playwright test dashboard-readiness-fit.spec.js --project=chromium
 */
const { test, expect } = require("@playwright/test");

const BASE_URL = process.env.E2E_BASE_URL || "http://localhost:8000";
const USER = process.env.E2E_ADMIN_USER || "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD || "";

/* 1280 = 1920@150% / 1600@125%     1366 = 1708@125%     1536 = 1920@125% */
const VIEWPORTS = [1280, 1366, 1536];

test.describe.configure({ mode: "serial" });

async function login(page) {
  await page.goto(`${BASE_URL}/admin/login/`);
  await page.fill("#id_username", USER);
  await page.fill("#id_password", PASSWORD);
  await Promise.all([
    page.waitForURL(/\/admin\/(?!login)/),
    page.click('input[type="submit"], button[type="submit"]'),
  ]);
}

test("the readiness card fits the viewport and never scrolls sideways", async ({
  page,
}) => {
  test.setTimeout(120000);
  test.skip(!USER || !PASSWORD, "E2E_ADMIN_USER / E2E_ADMIN_PASSWORD not set");
  await login(page);

  for (const width of VIEWPORTS) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`${BASE_URL}/admin/`);
    await page.locator(".cusin-readiness, .cusin-readiness-list").first().waitFor();
    await page.waitForTimeout(300);
    await page.evaluate(() => document.fonts.ready);

    /* 1. the page itself fits */
    const doc = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      innerWidth: window.innerWidth,
    }));
    expect(
      doc.scrollWidth,
      `${width}px: horizontal overflow of ${doc.scrollWidth - doc.innerWidth}px`
    ).toBeLessThanOrEqual(doc.innerWidth);

    /* 2. every missing item is whole and inside the viewport */
    const rows = await page.evaluate(() =>
      [...document.querySelectorAll(".cusin-readiness-missing li")].map((el) => {
        const box = el.getBoundingClientRect();
        return {
          text: el.textContent.trim().slice(0, 50),
          left: Math.round(box.left),
          right: Math.round(box.right),
          width: Math.round(box.width),
          clipped: el.scrollWidth - el.clientWidth > 2,
          viewport: window.innerWidth + window.scrollX,
        };
      })
    );
    expect(rows.length, `${width}px: no readiness sub-list rendered`).toBeGreaterThan(0);

    const outside = rows.filter((row) => row.left < 0 || row.right > row.viewport);
    expect(outside, `${width}px: readiness items outside the viewport`).toEqual([]);

    const clipped = rows.filter((row) => row.clipped).map((row) => row.text);
    expect(clipped, `${width}px: clipped readiness text`).toEqual([]);

    /* 3. a row of the card is a full-width block, not a column */
    const geometry = await page.evaluate(() => {
      const list = document.querySelector(".cusin-readiness-list");
      const item = list && list.querySelector("li");
      const sub = item && item.querySelector(".cusin-readiness-missing");
      const cell = sub && sub.querySelector("li");
      const round = (element) => {
        const box = element.getBoundingClientRect();
        return {
          left: Math.round(box.left),
          right: Math.round(box.right),
          width: Math.round(box.width),
        };
      };
      return {
        list: round(list),
        item: round(item),
        sub: round(sub),
        cell: cell ? round(cell) : null,
      };
    });
    // RTL: the row's own box spans the card, so its edges match the list.
    expect(Math.abs(geometry.item.left - geometry.list.left), `${width}px: row inset`).toBeLessThanOrEqual(2);
    expect(Math.abs(geometry.item.right - geometry.list.right), `${width}px: row inset`).toBeLessThanOrEqual(2);
    // ...and the sub-list inside it is at least as wide as half the row.
    const rowWidth = geometry.item.right - geometry.item.left;
    const subWidth = geometry.sub.right - geometry.sub.left;
    expect(subWidth, `${width}px: sub-list squeezed beside the icon`).toBeGreaterThan(rowWidth * 0.6);
    expect(geometry.cell, `${width}px: no cell in the sub-list`).not.toBeNull();
    expect(geometry.cell.width, `${width}px: cell narrower than its minimum`).toBeGreaterThanOrEqual(200);
  }
});
