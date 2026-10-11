/**
 * Admin layout checks (follow-up 2): a real browser measures the Django admin
 * after login at four viewports. It asserts what a user would see go wrong:
 *   - the page never scrolls sideways (320, 375, 1280, 1440);
 *   - the dashboard fills its column on desktop (#content wider than 800px at 1280);
 *   - the object tools do not overlap the search card (#toolbar).
 * Follow-up 3 adds three checks, which need data in the database:
 *   - the changelist header sits above the first body row at 1024, 1280 and
 *     1440 (products, categories and orders; each needs at least one row);
 *   - the order change form does not scroll sideways at 320 and 375 (the
 *     first order in the orders changelist is used; create one first);
 *   - at 1280 a dashboard KPI with a 9-digit amount stays on one line, and the
 *     print and delete links on the order form keep 4.5:1 in normal, hover
 *     and focus. Both need at least one order with a total of 100,000,000 or
 *     more (for example, the order made by seed data plus one large order).
 *
 * Like the storefront suite this is NOT part of `npm test` (vitest) or
 * `manage.py test`: it needs a running backend and a browser. Set
 *   E2E_BASE_URL          the running admin origin (default http://localhost:8000)
 *   E2E_ADMIN_USER        a superuser's username
 *   E2E_ADMIN_PASSWORD    that user's password
 * The spec is skipped (with a visible reason) when the credentials are missing.
 * It runs in the desktop project only, because it sets its own viewports.
 */
const { test, expect } = require("@playwright/test");

const BASE_URL = process.env.E2E_BASE_URL || "http://localhost:8000";
const USER = process.env.E2E_ADMIN_USER || "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD || "";

const VIEWPORTS = [
  { width: 320, height: 640 },
  { width: 375, height: 740 },
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
];

const PAGES = [
  "/admin/",
  "/admin/products/product/",
  "/admin/categories/category/",
  "/admin/accounts/user/",
  "/admin/products/product/image-import/",
];

const CHANGELISTS = [
  "/admin/products/product/",
  "/admin/categories/category/",
  "/admin/accounts/user/",
];

async function login(page) {
  await page.goto(`${BASE_URL}/admin/login/`);
  await page.fill("#id_username", USER);
  await page.fill("#id_password", PASSWORD);
  await Promise.all([
    page.waitForURL(/\/admin\/(?!login)/),
    page.click('input[type="submit"], button[type="submit"]'),
  ]);
}

test.describe("admin layout after login", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");

  test.beforeEach(async ({ page }, testInfo) => {
    // desktop project only: this spec sets its own viewports
    test.skip(testInfo.project.name !== "chromium", "desktop project only");
    // one login per test; the session cookie is set on the page's context
    await login(page);
  });

  for (const viewport of VIEWPORTS) {
    test.describe(`${viewport.width}x${viewport.height}`, () => {
      test.use({ viewport });

      for (const path of PAGES) {
        test(`no sideways scrolling on ${path}`, async ({ page }) => {
          await page.goto(`${BASE_URL}${path}`, { waitUntil: "networkidle" });
          const { scrollWidth, clientWidth } = await page.evaluate(() => ({
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
          }));
          expect(scrollWidth, `scrollWidth ${scrollWidth} vs clientWidth ${clientWidth}`).toBeLessThanOrEqual(clientWidth);
        });
      }

      if (viewport.width >= 1280) {
        test("dashboard column is wider than 800px", async ({ page }) => {
          await page.goto(`${BASE_URL}/admin/`, { waitUntil: "networkidle" });
          const box = await page.locator("#content").boundingBox();
          expect(box, "#content must be rendered").not.toBeNull();
          expect(box.width).toBeGreaterThan(800);
        });
      }

      for (const path of CHANGELISTS) {
        test(`object tools do not overlap the search card on ${path}`, async ({ page }) => {
          await page.goto(`${BASE_URL}${path}`, { waitUntil: "networkidle" });
          const tools = await page.locator(".object-tools").first().boundingBox();
          const toolbar = await page.locator("#toolbar").first().boundingBox();
          expect(tools, ".object-tools must be rendered").not.toBeNull();
          expect(toolbar, "#toolbar must be rendered").not.toBeNull();
          const overlaps =
            tools.x < toolbar.x + toolbar.width &&
            toolbar.x < tools.x + tools.width &&
            tools.y < toolbar.y + toolbar.height &&
            toolbar.y < tools.y + tools.height;
          expect(overlaps, `object tools ${JSON.stringify(tools)} vs toolbar ${JSON.stringify(toolbar)}`).toBe(false);
        });
      }
    });
  }
});

/* -------------------------------------------------------------------------
 * Follow-up 3. Same login and skip rules as above.
 * ---------------------------------------------------------------------- */

const HEADER_PAGES = [
  "/admin/products/product/",
  "/admin/categories/category/",
  "/admin/orders/order/",
];

/** Change-page URL of the first order in the orders changelist. */
async function firstOrderUrl(page) {
  await page.goto(`${BASE_URL}/admin/orders/order/`, { waitUntil: "networkidle" });
  const link = page.locator('#result_list tbody a[href*="/change/"]').first();
  const href = await link.getAttribute("href");
  if (!href) {
    throw new Error("precondition: the orders changelist has no order; create one before this check");
  }
  return href;
}

/** Relative luminance and WCAG contrast for `rgb(r, g, b)` strings. */
function contrastOf(fg, bg) {
  const channels = (text) => text.match(/\d+(\.\d+)?/g).slice(0, 3).map(Number);
  const luminance = ([r, g, b]) => {
    const [R, G, B] = [r, g, b].map((c) => {
      const v = c / 255;
      return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * R + 0.7152 * G + 0.0722 * B;
  };
  const [a, b] = [luminance(channels(fg)), luminance(channels(bg))].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

test.describe("follow-up 3: changelist header row", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only");
    await login(page);
  });

  for (const width of [1024, 1280, 1440]) {
    test.describe(`${width}px`, () => {
      test.use({ viewport: { width, height: 900 } });

      for (const path of HEADER_PAGES) {
        test(`the header sits above the first body row on ${path}`, async ({ page }) => {
          await page.goto(`${BASE_URL}${path}`, { waitUntil: "networkidle" });
          await page.evaluate(() => window.scrollTo(0, 0));
          const measured = await page.evaluate(() => {
            const heads = [...document.querySelectorAll("#result_list thead th")];
            const cells = [...document.querySelectorAll("#result_list tbody tr:first-child > *")];
            if (!heads.length || !cells.length) return null;
            return {
              headBottom: Math.max(...heads.map((th) => th.getBoundingClientRect().bottom)),
              rowTop: Math.min(...cells.map((td) => td.getBoundingClientRect().top)),
            };
          });
          expect(measured, "changelist needs a header and at least one body row").not.toBeNull();
          expect(
            measured.headBottom,
            `header bottom ${measured.headBottom} must be at or above first row top ${measured.rowTop}`,
          ).toBeLessThanOrEqual(measured.rowTop + 0.5);
        });
      }
    });
  }
});

test.describe("follow-up 3: order change form at phone widths", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only");
    await login(page);
  });

  for (const width of [320, 375]) {
    test.describe(`${width}px`, () => {
      test.use({ viewport: { width, height: 740 } });

      test("the order form does not scroll sideways (items and inline tables scroll in their own wrapper)", async ({ page }) => {
        const url = await firstOrderUrl(page);
        await page.goto(`${BASE_URL}${url}`, { waitUntil: "networkidle" });
        const { scrollWidth, clientWidth } = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        }));
        expect(scrollWidth, `scrollWidth ${scrollWidth} vs clientWidth ${clientWidth}`).toBeLessThanOrEqual(clientWidth);
      });
    });
  }
});

test.describe("follow-up 3: dashboard amounts and order-form button contrast at 1280", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only");
    await login(page);
  });

  test.use({ viewport: { width: 1280, height: 800 } });

  test("a 9-digit KPI amount stays on one line and is not clipped", async ({ page }) => {
    await page.goto(`${BASE_URL}/admin/`, { waitUntil: "networkidle" });
    const kpis = await page.evaluate(() => {
      const lines = (el) => {
        const tops = new Set();
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
          if (!node.textContent.trim()) continue;
          const range = document.createRange();
          range.selectNodeContents(node);
          for (const rect of range.getClientRects()) tops.add(Math.round(rect.top));
        }
        return tops.size;
      };
      return [...document.querySelectorAll(".cusin-kpi")].map((kpi) => {
        const label = kpi.querySelector(".cusin-kpi-label");
        const value = kpi.querySelector(".cusin-kpi-value");
        return {
          value: value.textContent.trim(),
          labelLines: lines(label),
          valueLines: lines(value),
          valueScrollWidth: value.scrollWidth,
          valueClientWidth: value.clientWidth,
        };
      });
    });
    const nineDigit = kpis.filter((kpi) => /[۰-۹]{3}٬[۰-۹]{3}٬[۰-۹]{3}/.test(kpi.value));
    expect(nineDigit.length, "precondition: a dashboard KPI with a 9-digit amount (see the spec header)").toBeGreaterThan(0);
    for (const kpi of nineDigit) {
      expect(kpi.labelLines, `label of ${kpi.value}`).toBe(1);
      expect(kpi.valueLines, `value ${kpi.value}`).toBe(1);
      expect(kpi.valueScrollWidth, `value ${kpi.value} must not be clipped`).toBeLessThanOrEqual(kpi.valueClientWidth);
    }
  });

  test("the print and delete links keep 4.5:1 in normal, hover and focus", async ({ page }) => {
    const url = await firstOrderUrl(page);
    await page.goto(`${BASE_URL}${url}`, { waitUntil: "networkidle" });
    const print = page.locator("a.cusin-btn--dark").first();
    const del = page.locator(".submit-row a.deletelink").first();
    await expect(print, "print link must be rendered").toBeVisible();
    await expect(del, "delete link must be rendered").toBeVisible();

    const colours = async (locator) =>
      locator.evaluate((el) => {
        const cs = getComputedStyle(el);
        return { color: cs.color, background: cs.backgroundColor };
      });
    const checks = [
      ["print normal", print, async () => {}],
      ["print hover", print, async () => print.hover()],
      ["print focus", print, async () => print.evaluate((el) => el.focus())],
      ["delete normal", del, async () => {}],
      ["delete hover", del, async () => del.hover()],
      ["delete focus", del, async () => del.evaluate((el) => el.focus())],
    ];
    for (const [label, locator, prepare] of checks) {
      await page.mouse.move(0, 0);
      await locator.evaluate((el) => el.blur());
      await prepare();
      const { color, background } = await colours(locator);
      expect(contrastOf(color, background), `${label}: ${color} on ${background}`).toBeGreaterThanOrEqual(4.5);
    }
  });
});
