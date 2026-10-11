/*
 * Real-browser layout, accessibility and visual review of the Django admin.
 *
 * Set E2E_BASE_URL, E2E_ADMIN_USER and E2E_ADMIN_PASSWORD. Product and order
 * form checks, plus the screenshot review, require at least one product and
 * one order in the database. Screenshots are captured only when
 * E2E_CAPTURE_SCREENSHOTS=1 and go to e2e/screenshots/ for PR review.
 */
const fs = require("node:fs");
const path = require("node:path");
const { test, expect } = require("@playwright/test");

const BASE_URL = process.env.E2E_BASE_URL || "http://localhost:8000";
const USER = process.env.E2E_ADMIN_USER || "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD || "";
const CAPTURE_SCREENSHOTS = process.env.E2E_CAPTURE_SCREENSHOTS === "1";
const SCREENSHOT_DIR = path.join(__dirname, "screenshots");

const VIEWPORTS = [
  { width: 320, height: 700 },
  { width: 375, height: 812 },
  { width: 1024, height: 900 },
  { width: 1280, height: 900 },
  { width: 1440, height: 1000 },
];

const PAGES = [
  "/admin/",
  "/admin/products/product/",
  "/admin/categories/category/",
  "/admin/orders/order/",
  "/admin/accounts/user/",
];

const CHANGELISTS = PAGES.slice(1);

async function login(page) {
  await page.goto(`${BASE_URL}/admin/login/`);
  await page.fill("#id_username", USER);
  await page.fill("#id_password", PASSWORD);
  await Promise.all([
    page.waitForURL(/\/admin\/(?!login)/),
    page.click('input[type="submit"], button[type="submit"]'),
  ]);
}

async function firstChangeUrl(page, listPath, label) {
  await page.goto(`${BASE_URL}${listPath}`, { waitUntil: "networkidle" });
  const link = page.locator('#result_list tbody a[href*="/change/"]').first();
  const href = await link.getAttribute("href");
  if (!href) {
    throw new Error(`precondition: the ${label} changelist has no editable row; create one before this check`);
  }
  return href;
}

async function firstProductUrl(page) {
  return firstChangeUrl(page, "/admin/products/product/", "product");
}

async function firstOrderUrl(page) {
  return firstChangeUrl(page, "/admin/orders/order/", "order");
}

async function assertNoHorizontalOverflow(page) {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(scrollWidth, `scrollWidth ${scrollWidth} vs clientWidth ${clientWidth}`).toBeLessThanOrEqual(clientWidth);
}

async function assertAdminTypography(page) {
  const metrics = await page.evaluate(() => {
    const bodyStyle = getComputedStyle(document.body);
    const textElements = [...document.querySelectorAll("#container *")].filter((element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      const text = [element.innerText, element.value, element.getAttribute("placeholder")]
        .filter(Boolean).join(" ").trim();
      // Native select controls expose all option labels through innerText even
      // though only the selected value is visible; option-menu typography is
      // rendered by the browser and is not document line-height text.
      return element.tagName !== "OPTION" && element.tagName !== "SELECT" &&
        !element.classList.contains("select2-hidden-accessible") &&
        text && rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
    });
    const small = [];
    const tightPersian = [];
    for (const element of textElements) {
      const style = getComputedStyle(element);
      const size = parseFloat(style.fontSize);
      const text = [element.innerText, element.value, element.getAttribute("placeholder")]
        .filter(Boolean).join(" ").trim();
      if (size < 14) small.push({ text: text.slice(0, 40), size: style.fontSize });
      if (/[\u0600-\u06ff]/.test(text)) {
        const lineHeight = style.lineHeight === "normal" ? NaN : parseFloat(style.lineHeight) / size;
        if (!Number.isFinite(lineHeight) || lineHeight < 1.7) {
          tightPersian.push({ text: text.slice(0, 40), lineHeight: style.lineHeight, size: style.fontSize });
        }
      }
    }
    const bodySize = parseFloat(bodyStyle.fontSize);
    return {
      bodySize,
      bodyLineHeight: parseFloat(bodyStyle.lineHeight) / bodySize,
      small,
      tightPersian,
    };
  });
  expect(metrics.bodySize, "admin desktop base text should be 16px").toBe(16);
  expect(metrics.bodyLineHeight, "Persian body leading should be at least 1.7").toBeGreaterThanOrEqual(1.7);
  expect(metrics.small, "visible admin text below 14px").toEqual([]);
  expect(metrics.tightPersian, "Persian text with line-height below 1.7").toEqual([]);
}

async function assertPanelInViewport(page, selector) {
  const panel = page.locator(selector);
  await expect(panel, `${selector} should be open`).toBeVisible();
  const rect = await panel.evaluate((el) => {
    const box = el.getBoundingClientRect();
    return { left: box.left, top: box.top, right: box.right, bottom: box.bottom };
  });
  const viewport = page.viewportSize();
  expect(rect.left, `${selector} left edge`).toBeGreaterThanOrEqual(0);
  expect(rect.top, `${selector} top edge`).toBeGreaterThanOrEqual(0);
  expect(rect.right, `${selector} right edge`).toBeLessThanOrEqual(viewport.width + 0.5);
  expect(rect.bottom, `${selector} bottom edge`).toBeLessThanOrEqual(viewport.height + 0.5);
}

/** Relative luminance and WCAG contrast for CSS rgb()/rgba() strings. */
function contrastOf(fg, bg) {
  const channels = (text) => text.match(/[\d.]+/g).slice(0, 3).map(Number);
  const luminance = ([r, g, b]) => {
    const [R, G, B] = [r, g, b].map((c) => {
      const v = c / 255;
      return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * R + 0.7152 * G + 0.0722 * B;
  };
  const [a, b] = [luminance(channels(fg)), luminance(channels(bg))].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

test.describe("admin pages at all requested viewport widths", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only; this spec sets its own viewport");
    await login(page);
  });

  for (const viewport of VIEWPORTS) {
    test.describe(`${viewport.width}x${viewport.height}`, () => {
      test.use({ viewport });

      for (const pagePath of PAGES) {
        test(`no horizontal page overflow on ${pagePath}`, async ({ page }) => {
          await page.goto(`${BASE_URL}${pagePath}`, { waitUntil: "networkidle" });
          await assertNoHorizontalOverflow(page);
          await assertAdminTypography(page);
        });
      }

      for (const form of [
        { label: "product", getUrl: firstProductUrl },
        { label: "order", getUrl: firstOrderUrl },
      ]) {
        test(`no horizontal overflow on the ${form.label} form`, async ({ page }) => {
          const url = await form.getUrl(page);
          await page.goto(new URL(url, BASE_URL).href, { waitUntil: "networkidle" });
          await assertNoHorizontalOverflow(page);
          await assertAdminTypography(page);
        });
      }

      if (viewport.width >= 1280) {
        test("dashboard content fills the desktop column", async ({ page }) => {
          await page.goto(`${BASE_URL}/admin/`, { waitUntil: "networkidle" });
          const box = await page.locator("#content").boundingBox();
          expect(box, "#content must be rendered").not.toBeNull();
          expect(box.width).toBeGreaterThan(800);
        });
      }

      for (const pagePath of CHANGELISTS) {
        test(`object tools do not overlap the search toolbar on ${pagePath}`, async ({ page }) => {
          await page.goto(`${BASE_URL}${pagePath}`, { waitUntil: "networkidle" });
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

      test("body text is at least 7:1 on page and white surfaces", async ({ page }) => {
        await page.goto(`${BASE_URL}/admin/`, { waitUntil: "networkidle" });
        const colors = await page.evaluate(() => ({
          text: getComputedStyle(document.body).color,
          page: getComputedStyle(document.querySelector("#container")).backgroundColor,
          surface: getComputedStyle(document.querySelector("#header")).backgroundColor,
        }));
        expect(contrastOf(colors.text, colors.page), `body ${colors.text} on page ${colors.page}`).toBeGreaterThanOrEqual(7);
        expect(contrastOf(colors.text, colors.surface), `body ${colors.text} on white surface ${colors.surface}`).toBeGreaterThanOrEqual(7);
      });
    });
  }
});

test.describe("shared menus and phone navigation", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only; this spec sets its own viewport");
    await login(page);
  });

  for (const viewport of VIEWPORTS) {
    test.describe(`${viewport.width}px`, () => {
      test.use({ viewport });

      test("user menu opens inside the viewport and Escape closes it with focus return", async ({ page }) => {
        await page.goto(`${BASE_URL}/admin/products/product/`, { waitUntil: "networkidle" });
        const trigger = page.locator("#cusin-user-menu-trigger");
        await trigger.click();
        await expect(trigger).toHaveAttribute("aria-expanded", "true");
        await assertPanelInViewport(page, "#cusin-user-menu");
        await page.keyboard.press("Escape");
        await expect(page.locator("#cusin-user-menu")).toBeHidden();
        await expect(trigger).toHaveAttribute("aria-expanded", "false");
        await expect(trigger).toBeFocused();
      });

      test("filter and bulk action menus remain in the viewport and close on Escape", async ({ page }) => {
        await page.goto(`${BASE_URL}/admin/products/product/`, { waitUntil: "networkidle" });
        const filterTrigger = page.locator(".cusin-filter-menu [data-cusin-menu-trigger]");
        await expect(filterTrigger, "product filters must be available").toBeVisible();
        await filterTrigger.click();
        const filterPanel = page.locator("#cusin-menu-panel-filters");
        if (viewport.width <= 480) {
          await expect(filterPanel).toHaveClass(/is-sheet/);
        } else {
          await expect(filterPanel).not.toHaveClass(/is-sheet/);
          const panelWidth = await filterPanel.evaluate((el) => el.getBoundingClientRect().width);
          expect(panelWidth, "desktop filters should remain a bounded popover").toBeLessThanOrEqual(500);
        }
        await assertPanelInViewport(page, "#cusin-menu-panel-filters");
        await page.keyboard.press("Escape");
        await expect(page.locator("#cusin-menu-panel-filters")).toBeHidden();
        await expect(filterTrigger).toHaveAttribute("aria-expanded", "false");

        const bulkTrigger = page.locator(".cusin-bulk-menu [data-cusin-menu-trigger]").first();
        await expect(bulkTrigger, "Django bulk actions must be available").toBeVisible();
        await bulkTrigger.click();
        const bulkPanel = page.locator("#cusin-menu-panel-bulk-actions-0");
        await assertPanelInViewport(page, "#cusin-menu-panel-bulk-actions-0");
        await page.keyboard.press("Escape");
        await expect(bulkPanel).toBeHidden();
        await expect(bulkTrigger).toHaveAttribute("aria-expanded", "false");
      });
    });
  }

  for (const viewport of VIEWPORTS.filter(({ width }) => width <= 375)) {
    test.describe(`phone drawer ${viewport.width}px`, () => {
      test.use({ viewport });

      test("opens the RTL drawer inside the viewport and closes it with Escape", async ({ page }) => {
        await page.goto(`${BASE_URL}/admin/`, { waitUntil: "networkidle" });
        const toggle = page.locator("#cusin-drawer-toggle");
        await expect(toggle).toBeVisible();
        await toggle.click();
        await expect(toggle).toHaveAttribute("aria-expanded", "true");
        const drawer = page.locator("#cusin-drawer");
        await expect(drawer).toHaveClass(/is-open/);
        await drawer.evaluate(async (el) => {
          await Promise.all(el.getAnimations().map((animation) => animation.finished.catch(() => {})));
        });
        const rect = await drawer.evaluate((el) => {
          const box = el.getBoundingClientRect();
          return { left: box.left, right: box.right, width: box.width };
        });
        expect(rect.left).toBeGreaterThanOrEqual(-0.5);
        expect(rect.right).toBeLessThanOrEqual(viewport.width + 0.5);
        expect(rect.width).toBeGreaterThan(0);
        await page.keyboard.press("Escape");
        await expect(drawer).not.toHaveClass(/is-open/);
        await expect(toggle).toHaveAttribute("aria-expanded", "false");
      });
    });
  }
});

test.describe("light theme is independent of the operating-system color scheme", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only");
    await login(page);
  });

  test.use({ viewport: { width: 1280, height: 900 }, colorScheme: "dark" });

  test("stays light while prefers-color-scheme is dark", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goto(`${BASE_URL}/admin/`, { waitUntil: "networkidle" });
    const appearance = await page.evaluate(() => ({
      darkPreference: matchMedia("(prefers-color-scheme: dark)").matches,
      meta: document.querySelector('meta[name="color-scheme"]')?.content,
      body: getComputedStyle(document.body).color,
      page: getComputedStyle(document.querySelector("#container")).backgroundColor,
      header: getComputedStyle(document.querySelector("#header")).backgroundColor,
      drawer: getComputedStyle(document.querySelector("#cusin-drawer")).backgroundColor,
      rootScheme: getComputedStyle(document.documentElement).colorScheme,
    }));
    expect(appearance.darkPreference).toBe(true);
    expect(appearance.meta).toBe("light");
    expect(appearance.body).toBe("rgb(17, 24, 39)");
    expect(appearance.page).toBe("rgb(245, 246, 248)");
    expect(appearance.header).toBe("rgb(255, 255, 255)");
    expect(appearance.drawer).toBe("rgb(255, 255, 255)");
    expect(appearance.rootScheme).toBe("light");
  });
});

/*
 * Screenshot review is opt-in so routine E2E runs do not add generated files.
 * Set E2E_CAPTURE_SCREENSHOTS=1 to save the actual product/order data views
 * and open menus that are requested for PR visual review.
 */
test.describe("visual review screenshots for the PR", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");
  test.skip(!CAPTURE_SCREENSHOTS, "set E2E_CAPTURE_SCREENSHOTS=1 to write review screenshots");

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only");
    await login(page);
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  for (const viewport of [{ width: 1280, height: 900 }, { width: 375, height: 812 }]) {
    test.describe(`${viewport.width}px`, () => {
      test.use({ viewport });

      test("dashboard, product/order lists and forms", async ({ page }) => {
        const shots = [
          ["dashboard", "/admin/"],
          ["products", "/admin/products/product/"],
          ["orders", "/admin/orders/order/"],
        ];
        for (const [name, pagePath] of shots) {
          await page.goto(`${BASE_URL}${pagePath}`, { waitUntil: "networkidle" });
          await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${viewport.width}-${name}.png`), fullPage: true });
        }
        const productUrl = await firstProductUrl(page);
        await page.goto(new URL(productUrl, BASE_URL).href, { waitUntil: "networkidle" });
        await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${viewport.width}-product-form.png`), fullPage: true });
        const orderUrl = await firstOrderUrl(page);
        await page.goto(new URL(orderUrl, BASE_URL).href, { waitUntil: "networkidle" });
        await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${viewport.width}-order-form.png`), fullPage: true });
      });

      test("open bulk-action, filter and user menus", async ({ page }) => {
        await page.goto(`${BASE_URL}/admin/products/product/`, { waitUntil: "networkidle" });
        const menuActions = [
          ["bulk-actions", ".cusin-bulk-menu [data-cusin-menu-trigger]", "#cusin-menu-panel-bulk-actions-0"],
          ["filters", ".cusin-filter-menu [data-cusin-menu-trigger]", "#cusin-menu-panel-filters"],
          ["user-menu", "#cusin-user-menu-trigger", "#cusin-user-menu"],
        ];
        for (const [name, triggerSelector, panelSelector] of menuActions) {
          const trigger = page.locator(triggerSelector).first();
          await trigger.click();
          await assertPanelInViewport(page, panelSelector);
          await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${viewport.width}-${name}-open.png`) });
          await page.keyboard.press("Escape");
          await expect(page.locator(panelSelector)).toBeHidden();
        }
      });

      if (viewport.width <= 375) {
        test("open phone navigation drawer", async ({ page }) => {
          await page.goto(`${BASE_URL}/admin/`, { waitUntil: "networkidle" });
          await page.locator("#cusin-drawer-toggle").click();
          const drawer = page.locator("#cusin-drawer");
          await expect(drawer).toHaveClass(/is-open/);
          await drawer.evaluate(async (el) => {
            await Promise.all(el.getAnimations().map((animation) => animation.finished.catch(() => {})));
          });
          await page.screenshot({ path: path.join(SCREENSHOT_DIR, "375-phone-drawer-open.png") });
        });
      }
    });
  }
});
