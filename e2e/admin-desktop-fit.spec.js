/*
 * Desktop fit review: the admin at the widths Windows actually reports.
 *
 * The bug this guards: at Windows 125%/150% display scaling the browser's
 * CSS viewport is SMALLER than the physical screen -- 1366px reports 1092
 * CSS px at 125% and 911 at 150%, 1920 reports 1536 and 1280. Those are
 * still desktop layouts, but the fixed type scale and paddings that fit
 * at 1920 CSS px overflow their cards and clip their labels there.
 *
 * What is checked, at each width, on the dashboard, the product and order
 * changelists and their change forms:
 *
 *   1. no element overflows the document horizontally (no sideways scroll);
 *   2. no TEXT is clipped -- an element whose content is wider/taller than
 *      its box and that is not allowed to scroll or wrap is a failure;
 *   3. the changelist row menu («…») opens fully INSIDE the viewport, and
 *      every one of its labels is rendered whole (not «وی»/«چا»/«حذ»);
 *   4. the sidebar's own header is never hidden under the sticky topbar.
 *
 * Requires a running stack and an admin account:
 *   E2E_BASE_URL, E2E_ADMIN_USER, E2E_ADMIN_PASSWORD
 * Optionally E2E_CAPTURE_SCREENSHOTS=1 to write before/after shots.
 *
 * Run with: npx playwright test admin-desktop-fit.spec.js --project=chromium
 */
const fs = require("node:fs");
const path = require("node:path");
const { test, expect } = require("@playwright/test");

const BASE_URL = process.env.E2E_BASE_URL || "http://localhost:8000";
const USER = process.env.E2E_ADMIN_USER || "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD || "";
const CAPTURE = process.env.E2E_CAPTURE_SCREENSHOTS === "1";
const SHOT_DIR = path.join(__dirname, "screenshots");

/* 1280 = 1920@150% / 1600@125%     1366 = 1708@125%
   1536 = 1920@125%                 1920 = 1920@100% (control) */
const VIEWPORTS = [
  { width: 1280, height: 800, tag: "1280" },
  { width: 1366, height: 768, tag: "1366" },
  { width: 1536, height: 864, tag: "1536" },
  { width: 1920, height: 1080, tag: "1920" },
];

const PAGES = [
  { path: "/admin/", name: "dashboard" },
  { path: "/admin/products/product/", name: "product-list" },
  { path: "/admin/orders/order/", name: "order-list" },
];

const CHANGE_FORMS = [
  { list: "/admin/products/product/", name: "product-form" },
  { list: "/admin/orders/order/", name: "order-form" },
];

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

/**
 * Every element whose text is cut off by its own box.
 *
 * An element legitimately scrolls (overflow auto/scroll) or truncates with
 * an ellipsis; both are intentional and readable. A plain `hidden` box that
 * is smaller than its content, or a line-clamped one that has lost more
 * than its second line, is a real clip.
 */
const CLIPPED_TEXT = () => {
  const offenders = [];
  const describe = (el) =>
    `${el.tagName.toLowerCase()}${el.className && typeof el.className === "string"
      ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".")
      : ""}`.slice(0, 80);

  for (const el of document.querySelectorAll(
    "h1, h2, h3, h4, th, td, label, p, span, strong, b, a, button, summary, li"
  )) {
    if (!el.textContent || !el.textContent.trim()) continue;
    // Only leaf-ish nodes: a wrapper is "overflowing" whenever a child is.
    if (el.querySelector("h1,h2,h3,h4,td,th,p,span,strong,b,a,button,summary,li")) continue;
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    if (style.overflow === "auto" || style.overflow === "scroll") continue;
    if (style.overflowY === "auto" || style.overflowY === "scroll") continue;
    if (style.textOverflow === "ellipsis") continue;
    const clipsX =
      el.scrollWidth - el.clientWidth > 2 &&
      ["hidden", "clip"].includes(style.overflowX);
    const clipsY =
      el.scrollHeight - el.clientHeight > 2 &&
      ["hidden", "clip"].includes(style.overflowY) &&
      // A deliberate 2-line clamp is a design choice, not a clip.
      !("-webkit-line-clamp" in style && style.webkitLineClamp !== "none");
    if (clipsX || clipsY) {
      offenders.push({
        tag: describe(el),
        text: el.textContent.trim().slice(0, 60),
        axis: clipsX ? "x" : "y",
        scrollW: el.scrollWidth,
        clientW: el.clientWidth,
        scrollH: el.scrollHeight,
        clientH: el.clientHeight,
      });
    }
  }
  return offenders;
};

async function expectNoOverflow(page, label, width) {
  const overflow = await page.evaluate(() => ({
    docWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(
    overflow.docWidth,
    `${label}@${width}: the page scrolls sideways (${overflow.docWidth} > ${overflow.clientWidth})`
  ).toBeLessThanOrEqual(overflow.clientWidth + 1);
}

async function expectNoClippedText(page, label, width) {
  const clipped = await page.evaluate(CLIPPED_TEXT);
  expect(
    clipped,
    `${label}@${width}: clipped text -> ${JSON.stringify(clipped.slice(0, 6))}`
  ).toEqual([]);
}

async function shoot(page, name) {
  if (!CAPTURE) return;
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  await page.screenshot({
    path: path.join(SHOT_DIR, `${name}.png`),
    fullPage: false,
  });
}

test.beforeEach(async ({ page }) => {
  test.skip(!USER || !PASSWORD, "E2E_ADMIN_USER / E2E_ADMIN_PASSWORD are required");
  await login(page);
});

for (const viewport of VIEWPORTS) {
  test.describe(`${viewport.width}px`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const target of PAGES) {
      test(`${target.name}: fits without clipped text`, async ({ page }) => {
        await page.goto(`${BASE_URL}${target.path}`, { waitUntil: "networkidle" });
        await page.waitForTimeout(150); // let the deferred theme.js settle
        await expectNoOverflow(page, target.name, viewport.tag);
        await expectNoClippedText(page, target.name, viewport.tag);
        await shoot(page, `${target.name}-${viewport.tag}`);
      });
    }

    test("sidebar header never hides under the sticky topbar", async ({ page }) => {
      await page.goto(`${BASE_URL}/admin/`, { waitUntil: "networkidle" });
      await page.waitForTimeout(150);
      const boxes = await page.evaluate(() => {
        const header = document.getElementById("header");
        const drawer = document.getElementById("cusin-drawer");
        if (!header || !drawer) return null;
        return {
          headerBottom: header.getBoundingClientRect().bottom,
          drawerTop: drawer.getBoundingClientRect().top,
          drawerHeadTop: drawer
            .querySelector(".cusin-drawer-head")
            .getBoundingClientRect().top,
        };
      });
      expect(boxes, "the themed admin must render a header and a drawer").not.toBeNull();
      expect(
        boxes.drawerTop,
        `the drawer starts under the topbar (${boxes.drawerTop} < ${boxes.headerBottom})`
      ).toBeGreaterThanOrEqual(boxes.headerBottom - 1);
      expect(
        boxes.drawerHeadTop,
        "the «پنل مدیریت» heading is hidden behind the topbar"
      ).toBeGreaterThanOrEqual(boxes.headerBottom - 1);
    });

    for (const target of CHANGE_FORMS) {
      test(`${target.name}: fits without clipped text`, async ({ page }) => {
        await page.goto(`${BASE_URL}${target.list}`, { waitUntil: "networkidle" });
        const href = await page
          .locator('#result_list tbody a[href*="/change/"]')
          .first()
          .getAttribute("href");
        expect(href, `precondition: ${target.list} needs at least one row`).toBeTruthy();
        await page.goto(`${BASE_URL}${href}`, { waitUntil: "networkidle" });
        await page.waitForTimeout(150);
        await expectNoOverflow(page, target.name, viewport.tag);
        await expectNoClippedText(page, target.name, viewport.tag);
        await shoot(page, `${target.name}-${viewport.tag}`);
      });
    }

    test("row action menu opens inside the viewport with whole labels", async ({ page }) => {
      await page.goto(`${BASE_URL}/admin/products/product/`, {
        waitUntil: "networkidle",
      });
      await page.waitForTimeout(150);
      const triggers = page.locator(".cusin-row-actions .cusin-row-more");
      const count = await triggers.count();
      expect(count, "precondition: the product changelist needs rows").toBeGreaterThan(0);

      // The LAST row is the worst case: it is nearest the bottom edge.
      for (const index of [0, count - 1]) {
        await triggers.nth(index).click();
        const panel = page.locator(".cusin-row-actions .cusin-menu-panel:not([hidden])").first();
        await panel.waitFor({ state: "visible" });

        const geo = await panel.evaluate((el) => {
          const r = el.getBoundingClientRect();
          const items = Array.from(el.querySelectorAll(".cusin-menu-item")).map(
            (item) => ({
              text: (item.textContent || "").trim(),
              clipped: item.scrollWidth - item.clientWidth > 2,
            })
          );
          return {
            left: r.left,
            right: r.right,
            top: r.top,
            bottom: r.bottom,
            vw: document.documentElement.clientWidth,
            vh: document.documentElement.clientHeight,
            items,
          };
        });

        expect(geo.left, `row ${index}: menu opens off-screen left`).toBeGreaterThanOrEqual(-1);
        expect(geo.right, `row ${index}: menu opens off-screen right`).toBeLessThanOrEqual(geo.vw + 1);
        expect(geo.top, `row ${index}: menu opens above the viewport`).toBeGreaterThanOrEqual(-1);
        expect(geo.bottom, `row ${index}: menu hangs below the fold`).toBeLessThanOrEqual(geo.vh + 1);

        const labels = geo.items.map((i) => i.text);
        expect(labels, `row ${index}: the menu has no items`).not.toHaveLength(0);
        for (const item of geo.items) {
          expect(
            item.clipped,
            `row ${index}: «${item.text}» is clipped inside the menu`
          ).toBe(false);
          // The reported symptom: labels cut down to one syllable.
          expect(item.text.length, `row ${index}: «${item.text}» is truncated`).toBeGreaterThan(1);
        }
        await shoot(page, `row-menu-${viewport.tag}-row${index}`);
        await page.keyboard.press("Escape");
      }
    });
  });
}
