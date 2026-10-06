/**
 * Cusin Gallery end-to-end flows (Part R3).
 *
 * NOT part of `npm test` or `manage.py test`. Drives a real browser against
 * the running stack (Django backend + Vite frontend, PAYMENT_GATEWAY=mock).
 * Bring-up instructions: docs/E2E.md.
 *
 * Flows covered:
 *   1. home page smoke (rows + featured brand tiles render),
 *   2. guest add-to-cart,
 *   3. register, guest cart merges into the new session,
 *   4. optional coupon at checkout (E2E_COUPON),
 *   5. checkout with EACH shipping method (standard, express, pickup)
 *      through the mock gateway,
 *   6. the paid orders appear in /account/orders/.
 */
const { test, expect } = require("@playwright/test");

// A fresh account per run so the suite can repeat against the same DB.
const PHONE = "+989" + String(Math.floor(100000000 + Math.random() * 899999999));
const PASSWORD = "e2e-cusin-2026!";
const COUPON = process.env.E2E_COUPON || "";

const ADDRESS = {
  recipient_name: "مشتری آزمایشی",
  phone: PHONE,
  province: "تهران",
  city: "تهران",
  address: "خیابان ولیعصر، پلاک ۱۰",
  postal_code: "1234567890",
};

/** Open the first product from the shop grid and land on its page. */
async function gotoFirstProduct(page) {
  await page.goto("/shop/");
  await page.locator('a[href^="/products/"]').first().click();
  await expect(page.locator("h1")).toBeVisible();
}

/** Click the main add-to-cart button, choosing the first variant if any. */
async function addToCart(page) {
  const main = page.getByRole("button", { name: /افزودن به سبد خرید|انتخاب گزینه‌ها/ }).first();
  await main.click();
  if (await page.getByText("به سبد خرید اضافه شد.").isVisible().catch(() => false)) return;
  // Variant required: pick the first option chip of each group, then add.
  for (const chip of await page.locator(".variant-option, .product-options button").all()) {
    if (await chip.isVisible()) {
      await chip.first().click();
      break;
    }
  }
  await page.getByRole("button", { name: "افزودن به سبد خرید" }).first().click();
  await expect(page.getByText("به سبد خرید اضافه شد.")).toBeVisible({ timeout: 15_000 });
}

/** Fill the checkout AddressForm (province/city selects, Part R3). */
async function fillAddress(page) {
  await page.locator("select").filter({ has: page.getByText("انتخاب استان…") }).selectOption(ADDRESS.province);
  await page.locator("select").filter({ has: page.getByText("انتخاب شهر…") }).selectOption(ADDRESS.city);
  await page.getByLabel("نام گیرنده").fill(ADDRESS.recipient_name);
  await page.getByLabel("شماره تماس").fill(ADDRESS.phone);
  await page.getByLabel("آدرس کامل").fill(ADDRESS.address);
  await page.getByLabel("کد پستی").fill(ADDRESS.postal_code);
}

/** Place the current checkout order, pay on the mock gateway, assert success. */
async function placeAndPay(page, testInfo) {
  await page.getByRole("button", { name: "ثبت سفارش" }).click();
  // Mock gateway page (served by Django) shows the amount + pay/cancel.
  await page.getByRole("link", { name: "پرداخت" }).click();
  await expect(page.getByText("پرداخت با موفقیت انجام شد")).toBeVisible({ timeout: 20_000 });
  await page.screenshot({
    path: testInfo.outputPath(`paid-${Date.now()}.png`),
    fullPage: true,
  });
}

test.describe.configure({ mode: "serial" });

test("home renders hero rows and featured brand tiles", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("banner")).toBeVisible();
  // Featured brand tiles (Part R2) link to /shop/?brand=<slug>.
  await expect(page.locator('a[href*="/shop/?brand="]').first()).toBeVisible({ timeout: 15_000 });
});

test("guest add-to-cart, register, cart merges", async ({ page }) => {
  await gotoFirstProduct(page);
  await addToCart(page);
  await expect(page.locator('a[href="/cart/"]')).toContainText("۱");

  await page.goto("/register/");
  await page.getByLabel("شماره موبایل").fill(PHONE);
  await page.getByLabel("نام").fill("مشتری");
  await page.getByLabel("نام خانوادگی").fill("آزمایشی");
  await page.getByLabel("رمز عبور", { exact: true }).fill(PASSWORD);
  await page.getByLabel("تکرار رمز عبور").fill(PASSWORD);
  await page.getByRole("button", { name: "ثبت‌نام" }).click();
  await expect(page).toHaveURL("/", { timeout: 15_000 });

  // The guest line must survive the login (server-side merge).
  await page.goto("/cart/");
  await expect(page.getByText("سبد خرید شما خالی است.")).toHaveCount(0);
});

test("checkout: standard shipping with coupon", async ({ page, context }, testInfo) => {
  await page.goto("/login/");
  await page.getByLabel("شماره موبایل یا ایمیل").fill(PHONE);
  await page.getByLabel("رمز عبور").fill(PASSWORD);
  await page.getByRole("button", { name: "ورود" }).click();
  await expect(page).toHaveURL("/", { timeout: 15_000 });

  await page.goto("/checkout/");
  await fillAddress(page);

  if (COUPON) {
    await page.getByLabel("کد تخفیف").fill(COUPON);
    await page.getByRole("button", { name: "اعمال" }).click();
    await expect(page.getByText(/اعمال شد/)).toBeVisible({ timeout: 10_000 });
  } else {
    testInfo.annotations.push({ type: "info", description: "E2E_COUPON not set -- coupon step skipped" });
  }

  await page.getByLabel("ارسال عادی").check();
  await placeAndPay(page, testInfo);
});

test("checkout: express shipping", async ({ page }, testInfo) => {
  await page.goto("/checkout/");
  await fillAddress(page);
  await page.getByLabel("ارسال اکسپرس").check();
  await placeAndPay(page, testInfo);
});

test("checkout: pickup", async ({ page }, testInfo) => {
  await page.goto("/checkout/");
  await page.getByLabel("دریافت حضوری").check();
  await page.getByLabel("نام گیرنده").first().fill(ADDRESS.recipient_name);
  await page.getByLabel("شماره تماس").first().fill(ADDRESS.phone);
  await placeAndPay(page, testInfo);
});

test("all paid orders are listed in the account", async ({ page }) => {
  await page.goto("/account/orders/");
  const rows = page.locator('a[href*="/account/orders/"]');
  await expect(rows.first()).toBeVisible({ timeout: 15_000 });
  const count = await rows.count();
  expect(count, "expected the three paid orders").toBeGreaterThanOrEqual(3);
});
