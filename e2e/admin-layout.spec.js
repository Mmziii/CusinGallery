/**
 * Admin layout checks (follow-up 2): a real browser measures the Django admin
 * after login at four viewports. It asserts what a user would see go wrong:
 *   - the page never scrolls sideways (320, 375, 1280, 1440);
 *   - the dashboard fills its column on desktop (#content wider than 800px at 1280);
 *   - the object tools do not overlap the search card (#toolbar).
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
