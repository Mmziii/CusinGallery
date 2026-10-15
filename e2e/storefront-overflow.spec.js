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
          if ((el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0) || (el.scrollHeight > el.clientHeight + 2 && el.clientHeight > 0)) result.push(`${el.tagName}.${el.className}: ${el.textContent.trim().slice(0,80)}`);
        }
        return result;
      });
      expect(failures, `${width}px ${path}`).toEqual([]);
    }
  }
});

test("product cards reserve equal name and brand heights with aligned prices", async ({ page }) => {
  await page.setViewportSize({width:1366,height:1000});
  await page.goto("/shop/");
  await page.locator(".product-card__name").first().waitFor();
  await page.waitForTimeout(500);
  const rows = await page.locator(".product-card").evaluateAll(cards => cards.map(card => {
    const rect = card.getBoundingClientRect();
    const name = card.querySelector(".product-card__name").getBoundingClientRect();
    const brand = card.querySelector(".product-card__brand").getBoundingClientRect();
    const price = card.querySelector(".price").getBoundingClientRect();
    return {top:rect.top, nameHeight:name.height, brandHeight:brand.height, priceTop:price.top};
  }));
  expect(rows.length).toBeGreaterThan(1);
  for (const row of rows) {
    expect(Math.abs(row.nameHeight - rows[0].nameHeight)).toBeLessThan(1);
    expect(Math.abs(row.brandHeight - rows[0].brandHeight)).toBeLessThan(1);
    for (const peer of rows.filter(peer => Math.abs(peer.top - row.top) < 2)) {
      expect(Math.abs(peer.priceTop - row.priceTop)).toBeLessThan(2);
    }
  }
});

test("wordmark and stock badge contrast pass and reduced motion disables new animation", async ({ page }) => {
  await page.emulateMedia({reducedMotion:"reduce"});
  await page.goto("/shop/");
  await page.locator(".badge--low").first().waitFor();
  const ratios = await page.evaluate(() => {
    const luminance = color => {
      const rgb = color.match(/[\d.]+/g).slice(0,3).map(Number).map(c => c / 255).map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4);
      return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
    };
    return [".site-header__brand-name", ".badge--low"].map(selector => {
      const el = document.querySelector(selector);
      let parent = el;
      while (getComputedStyle(parent).backgroundColor === "rgba(0, 0, 0, 0)") parent = parent.parentElement;
      const values = [luminance(getComputedStyle(el).color), luminance(getComputedStyle(parent).backgroundColor)].sort((a,b) => b-a);
      return (values[0]+.05)/(values[1]+.05);
    });
  });
  for (const ratio of ratios) expect(ratio).toBeGreaterThanOrEqual(4.5);
  expect(await page.locator("main").evaluate(el => getComputedStyle(el).animationName)).toBe("none");
});
