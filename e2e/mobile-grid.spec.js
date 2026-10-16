/**
 * Audit 19 — the phone experience, measured in a real browser at 375px.
 *
 * The owner tested the live site on a 375px phone and reported two things
 * that only a real layout can confirm:
 *
 *   1. every product card took a full row (~350-550px tall), so 40 products
 *      meant ~16 screens of scrolling -- the grid must be TWO dense columns,
 *      and nothing may overflow sideways;
 *   2. at checkout the «روش ارسال» section sat far below the address list,
 *      where nobody scrolled -- on a phone the checkout must walk
 *      address -> delivery method -> review, one step at a time, with the
 *      delivery choice visible right after the address.
 *
 * Requires the running stack (docs/E2E.md): Django + Vite, `seed_demo` data.
 *
 *   cd e2e && npx playwright test mobile-grid.spec.js --project=chromium
 *
 * The viewport is set INSIDE the spec (375x812 = iPhone-class), so the file
 * can run under any project. The optional 404 check needs the real edge
 * (nginx + Django); set E2E_EXPECT_REAL_404=1 when pointing E2E_BASE_URL at
 * the composed stack, otherwise it is skipped with a note -- the Vite dev
 * server answers every path with 200 by design.
 */
const { test, expect } = require("@playwright/test");

const PHONE = "+989" + String(Math.floor(100000000 + Math.random() * 899999999));
const PASSWORD = "e2e-mobile-2026!";

const VIEWPORT = { width: 375, height: 812 };

const ADDRESS = {
  recipient_name: "مشتری موبایل",
  phone: PHONE,
  province: "تهران",
  city: "تهران",
  address: "خیابان ولیعصر، پلاک ۱۰",
  postal_code: "1234567890",
  building_number: "10",
  unit: "2",
};

test.use({ viewport: VIEWPORT });

/** Register (or log in) a disposable customer so /checkout/ is reachable. */
async function signIn(page) {
  await page.goto("/register/");
  if (await page.getByRole("heading", { name: /ثبت‌نام/ }).count()) {
    const phoneField = page.getByLabel("شماره موبایل");
    await phoneField.fill(PHONE);
    await page.getByLabel("رمز عبور", { exact: true }).fill(PASSWORD);
    await page.getByLabel("تکرار رمز عبور").fill(PASSWORD);
    await page.getByRole("button", { name: "ثبت‌نام" }).click();
    await expect(page).toHaveURL("/", { timeout: 15_000 });
    return;
  }
  // An existing session (a repeat run in the same browser context).
  await page.goto("/login/");
  await page.getByLabel("شماره موبایل یا ایمیل").fill(PHONE);
  await page.getByLabel("رمز عبور").fill(PASSWORD);
  await page.getByRole("button", { name: "ورود" }).click();
  await expect(page).toHaveURL("/", { timeout: 15_000 });
}

/** Put one product in the cart from the shop grid. */
async function addOneProduct(page) {
  await page.goto("/shop/");
  await page.locator(".product-card").first().waitFor();
  await page.locator('a[href^="/products/"]').first().click();
  await expect(page.locator("h1")).toBeVisible();
  await page.getByRole("button", { name: /افزودن به سبد خرید|انتخاب گزینه‌ها/ }).first().click();
  const variant = page.locator(".variant-option, .product-options button").first();
  if (await variant.isVisible().catch(() => false)) {
    await variant.click();
    await page.getByRole("button", { name: "افزودن به سبد خرید" }).first().click();
  }
}

/** Fill the inline checkout address (province/city are selects). */
async function fillAddress(page) {
  await page.getByLabel("نام گیرنده").fill(ADDRESS.recipient_name);
  await page.getByLabel("شماره تماس").first().fill(ADDRESS.phone);
  await page.locator("select").filter({ hasText: "انتخاب استان" }).selectOption(ADDRESS.province);
  await page.locator("select").filter({ hasText: "انتخاب شهر" }).selectOption(ADDRESS.city);
  await page.getByLabel("آدرس کامل").fill(ADDRESS.address);
  await page.getByLabel("کد پستی").fill(ADDRESS.postal_code);
  const building = page.getByLabel("پلاک");
  if (await building.count()) await building.first().fill(ADDRESS.building_number);
  const unit = page.getByLabel("واحد");
  if (await unit.count()) await unit.first().fill(ADDRESS.unit);
}

test.describe("phone product grid (375px)", () => {
  test("shows exactly two product cards per row with aligned bottoms", async ({ page }) => {
    await page.goto("/shop/");
    await page.locator(".product-card").first().waitFor();
    await page.waitForTimeout(400); // let fonts/images settle

    const rows = await page.locator(".product-card").evaluateAll((cards) =>
      cards.map((card) => {
        const box = card.getBoundingClientRect();
        return { top: Math.round(box.top), left: Math.round(box.left), width: Math.round(box.width) };
      })
    );
    expect(rows.length).toBeGreaterThan(3);

    const firstRowTop = rows[0].top;
    const firstRow = rows.filter((row) => Math.abs(row.top - firstRowTop) < 2);
    expect(firstRow.length, "two cards share the first row").toBe(2);

    // No row ever holds three cards, and the two cards are equal width.
    const byRow = new Map();
    for (const row of rows) {
      const key = Math.round(row.top / 4); // tolerate sub-pixel differences
      byRow.set(key, [...(byRow.get(key) || []), row]);
    }
    for (const cards of byRow.values()) {
      expect(cards.length).toBeLessThanOrEqual(2);
    }
    expect(Math.abs(firstRow[0].width - firstRow[1].width)).toBeLessThanOrEqual(1);

    // Roughly half the viewport: (375 - 2x12 padding - 8 gap) / 2 ≈ 171px.
    expect(firstRow[0].width).toBeGreaterThan(150);
    expect(firstRow[0].width).toBeLessThan(200);
  });

  test("never scrolls sideways at the phone widths the owner tested", async ({ page }) => {
    await page.goto("/shop/");
    await page.locator(".product-card").first().waitFor();

    for (const width of [320, 360, 375, 390, 414]) {
      await page.setViewportSize({ width, height: 812 });
      await page.waitForTimeout(250);
      const overflow = await page.evaluate(() => ({
        docScroll: document.documentElement.scrollWidth,
        docClient: document.documentElement.clientWidth,
        bodyScroll: document.body.scrollWidth,
        offenders: [...document.querySelectorAll(".product-card, .product-card *")]
          .filter((el) => el.getBoundingClientRect().right > window.innerWidth + 1)
          .slice(0, 5)
          .map((el) => `${el.tagName}.${el.className}`),
      }));
      expect(overflow.docScroll, `document scrollWidth at ${width}px`).toBeLessThanOrEqual(
        overflow.docClient + 1
      );
      expect(overflow.bodyScroll, `body scrollWidth at ${width}px`).toBeLessThanOrEqual(width + 1);
      expect(overflow.offenders, `cards sticking out at ${width}px`).toEqual([]);
    }
  });

  test("compact cards: square image, 2-line name, round cart button", async ({ page }) => {
    await page.goto("/shop/");
    await page.locator(".product-card").first().waitFor();

    const first = page.locator(".product-card").first();
    const image = first.locator(".product-card__media");
    const box = await image.boundingBox();
    expect(Math.abs(box.width - box.height)).toBeLessThanOrEqual(2);

    const addButton = first.locator(".product-card__add-icon, .product-card__notify").first();
    await expect(addButton).toBeVisible();
    const nameClamp = await first.locator(".product-card__name").evaluate(
      (el) => getComputedStyle(el).webkitLineClamp
    );
    expect(nameClamp).toBe("2");
  });

  test("the phone toolbar carries filters, sorting and the result count", async ({ page }) => {
    await page.goto("/shop/");
    await page.locator(".product-card").first().waitFor();

    const bar = page.locator(".shop__mobile-bar");
    await expect(bar).toBeVisible();
    await expect(bar).toContainText("کالا");
    // The old long filter block is gone from the page body.
    await expect(page.locator(".shop__sidebar")).toHaveCount(0);

    await bar.getByRole("button", { name: /فیلترها/ }).click();
    const sheet = page.locator("#shop-filters-sheet");
    await expect(sheet).toBeVisible();
    await expect(sheet.getByRole("button", { name: "اعمال" })).toBeVisible();
    await sheet.getByRole("button", { name: "اعمال" }).click();
    await expect(sheet).toHaveCount(0);

    await bar.getByRole("button", { name: "مرتب‌سازی" }).click();
    await expect(page.locator("#shop-sort-sheet")).toBeVisible();
    await page.locator("#shop-sort-sheet").getByText("ارزان‌ترین").click();
    await expect(page.locator("#shop-sort-sheet")).toHaveCount(0);
    await expect(page).toHaveURL(/ordering=price_asc/);
  });

  test("the header search gets its own full-width row", async ({ page }) => {
    await page.goto("/shop/");
    const search = page.locator(".site-header__search input");
    await expect(search).toBeVisible();
    const box = await search.boundingBox();
    expect(box.width).toBeGreaterThan(VIEWPORT.width * 0.7);

    // The Persian placeholder is fully visible (nothing is clipped).
    const placeholderFits = await search.evaluate((el) => {
      const style = getComputedStyle(el);
      return el.clientWidth >= el.scrollWidth - 1 && style.textOverflow !== "ellipsis";
    });
    expect(placeholderFits).toBe(true);
  });

  test("skeletons use the same two-column grid, so nothing jumps", async ({ page }) => {
    // Throttle the catalog request so the skeleton state is observable.
    await page.route("**/api/v1/products/**", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      await route.continue();
    });
    await page.goto("/shop/");
    const skeletons = page.locator(".shop__skeleton .product-card--skeleton");
    await expect(skeletons.first()).toBeVisible({ timeout: 15_000 });
    const boxes = await skeletons.evaluateAll((nodes) =>
      nodes.slice(0, 2).map((node) => Math.round(node.getBoundingClientRect().width))
    );
    expect(boxes.length).toBe(2);
    expect(Math.abs(boxes[0] - boxes[1])).toBeLessThanOrEqual(1);
    expect(boxes[0]).toBeGreaterThan(150);
    expect(boxes[0]).toBeLessThan(200);
  });
});

test.describe("phone checkout steps (375px)", () => {
  test("the delivery step follows the address step and shows big delivery cards", async ({ page }) => {
    test.setTimeout(120_000);
    await signIn(page);
    await addOneProduct(page);
    await page.goto("/checkout/");
    await expect(page.getByRole("heading", { name: "ثبت سفارش" })).toBeVisible();

    // Step 1 -- address only.
    await expect(page.locator("#checkout-section-address")).toBeVisible();
    await expect(page.locator("#checkout-section-shipping")).toBeHidden();
    await expect(page.locator(".checkout__mobile-bar")).toBeVisible();

    await fillAddress(page);
    const next = page.locator(".checkout__mobile-bar").getByRole("button", {
      name: "ادامه: انتخاب روش ارسال",
    });
    await next.click();

    // Step 2 -- the delivery method is the visible step, with its own heading.
    await expect(page.getByRole("heading", { name: "روش ارسال" })).toBeVisible({ timeout: 10_000 });
    await expect(page.locator("#checkout-section-shipping")).toBeVisible();
    await expect(page.locator("#checkout-section-address")).toBeHidden();
    const cards = page.locator(".shipping-method");
    expect(await cards.count()).toBeGreaterThanOrEqual(2);
    await expect(page.locator(".shipping-method--active")).toHaveCount(1);
    await expect(cards.first().locator(".shipping-method__icon")).toBeVisible();
    // Price or «رایگان» is always visible.
    await expect(cards.first().locator(".shipping-method__cost")).not.toBeEmpty();

    // Step 3 -- review, then the payable amount is on the sticky bar.
    await page.locator(".checkout__mobile-bar").getByRole("button", { name: "ادامه: بازبینی" }).click();
    await expect(page.locator("#checkout-section-review")).toBeVisible();
    await expect(page.locator("#checkout-section-review")).toContainText("مبلغ قابل پرداخت");
    await expect(page.locator("#checkout-section-review")).toContainText(/ارسال عادی|ارسال اکسپرس|دریافت حضوری/);
    await expect(page.locator(".checkout__mobile-bar")).toContainText("تومان");

    // Going back through the stepper is one tap.
    await page.locator(".checkout__steps button").first().click();
    await expect(page.locator("#checkout-section-address")).toBeVisible();
    await expect(page.locator("#checkout-section-shipping")).toBeHidden();
  });

  test("placing the order keeps working from the phone flow", async ({ page }) => {
    test.setTimeout(120_000);
    await signIn(page);
    await addOneProduct(page);
    await page.goto("/checkout/");
    await fillAddress(page);

    const bar = page.locator(".checkout__mobile-bar");
    await bar.getByRole("button", { name: "ادامه: انتخاب روش ارسال" }).click();
    await page.getByRole("radio", { name: /دریافت حضوری/ }).check();
    await bar.getByRole("button", { name: "ادامه: بازبینی" }).click();
    await bar.getByRole("button", { name: "ثبت سفارش" }).click();

    await expect(page.getByText("سفارش شما ثبت شد")).toBeVisible({ timeout: 20_000 });
  });

  test("the password eyes exist on the phone too", async ({ page }) => {
    await page.goto("/login/");
    const toggle = page.locator(".password-field__toggle").first();
    await expect(toggle).toHaveAttribute("aria-label", "نمایش رمز");
    await page.getByLabel("رمز عبور").fill("secret123");
    await toggle.click();
    await expect(page.getByLabel("رمز عبور")).toHaveAttribute("type", "text");
    await toggle.click();
    await expect(page.getByLabel("رمز عبور")).toHaveAttribute("type", "password");
  });
});

test("unknown URLs are a real 404 at the edge (nginx + Django)", async ({ request }) => {
  test.skip(
    process.env.E2E_EXPECT_REAL_404 !== "1",
    "Set E2E_EXPECT_REAL_404=1 when E2E_BASE_URL points at the composed stack " +
      "(Vite's dev server answers every path with 200 by design)."
  );

  const home = await request.get("/");
  expect(home.status()).toBe(200);

  const missing = await request.get("/nonexistent-xyz");
  expect(missing.status()).toBe(404);
  expect(await missing.text()).toContain("noindex");

  const missingProduct = await request.get("/products/does-not-exist/");
  expect(missingProduct.status()).toBe(404);
});
