/** Real text geometry, not jsdom's zero-sized layout. Requires seed_demo. */
const { test, expect } = require("@playwright/test");
test("visible storefront text fits at all acceptance widths", async ({ page }) => {
  test.setTimeout(180000);
  await page.goto("/register/");
  await page.getByLabel("شماره موبایل").fill(`091${String(Date.now()).slice(-8)}`);
  await page.locator("input[type=password]").nth(0).fill("audit-pass123");
  await page.locator("input[type=password]").nth(1).fill("audit-pass123");
  await page.getByRole("button", { name: "ثبت‌نام", exact: true }).click();
  await expect(page).not.toHaveURL(/register/);
  await page.goto("/shop/");
  const productPath = await page.locator('.product-card__name').first().getAttribute("href");
  await page.goto(productPath);
  await page.getByRole("button", { name: "افزودن به سبد خرید", exact: true }).first().click();
  for (const width of [360,390,768,1280,1366,1920]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const path of ["/", "/shop/", productPath, "/cart/", "/checkout/", "/account/"]) {
      await page.goto(path);
      await page.locator("main").waitFor();
      await page.waitForTimeout(700);
      await page.evaluate(() => document.fonts.ready);
      const failures = await page.evaluate(() => {
        const result = [];
        for (const el of document.querySelectorAll("main *, header *, footer *")) {
          const cs = getComputedStyle(el), box = el.getBoundingClientRect();
          if (!box.width || !box.height || cs.visibility === "hidden" || cs.display === "none" || Number(cs.opacity) === 0) continue;
          if (box.right < 0 || box.left > innerWidth || el.closest('[aria-hidden="true"],.sr-only,.visually-hidden')) continue;
          if (![...el.childNodes].some(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim())) continue;
          // Ellipsis/clamping is intentional, accessible truncation.
          if (cs.textOverflow === "ellipsis" || Number(cs.webkitLineClamp) > 0) continue;
          if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0) result.push(`${el.tagName}.${el.className}: ${el.textContent.trim().slice(0,80)}`);
        }
        return result;
      });
      expect(failures, `${width}px ${path}`).toEqual([]);
    }
  }
});
