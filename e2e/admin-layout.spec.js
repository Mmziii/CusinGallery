/*
 * Real-browser layout, accessibility and visual review of the Django admin.
 *
 * Set E2E_BASE_URL, E2E_ADMIN_USER and E2E_ADMIN_PASSWORD. Product and order
 * form checks require at least one product and order; desktop changelist
 * checks require at least one row in each of the six target admin lists.
 * Screenshots are captured only when
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
  { width: 768, height: 900 },
  { width: 1024, height: 900 },
  { width: 1280, height: 900 },
  { width: 1440, height: 1000 },
  { width: 1920, height: 1000 },
];

const PAGES = [
  "/admin/",
  "/admin/products/product/",
  "/admin/categories/category/",
  "/admin/orders/order/",
  "/admin/accounts/user/",
  "/admin/discounts/coupon/",
  "/admin/reviews/review/",
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

async function firstProductVariantUrl(page) {
  return firstChangeUrl(page, "/admin/products/productvariant/", "product variant");
}

async function firstUserUrl(page) {
  return firstChangeUrl(page, "/admin/accounts/user/", "user");
}

async function firstProductWithVariantsUrl(page) {
  return firstChangeUrl(page, "/admin/products/product/?q=MUG-300", "product with variants");
}

async function firstCartUrl(page) {
  return firstChangeUrl(page, "/admin/cart/cart/", "cart");
}

const LAYOUT_FIXTURE_NAME =
  "ماگ سرامیکی دسته‌دار دست‌ساز با لعاب رنگی ویژه برای سرو قهوه، چای و نوشیدنی‌های گرم در خانه و محل کار";
let productLayoutFixtureOriginal = null;

async function saveProductLayoutFixture(page, values) {
  const href = await firstProductWithVariantsUrl(page);
  await page.goto(new URL(href, BASE_URL).href, { waitUntil: "networkidle" });
  await page.locator("#id_name").fill(values.name);
  await page.locator("#id_price").fill(values.price);
  await page.locator("#id_compare_at_price").fill(values.compareAt);
  await Promise.all([
    page.waitForLoadState("networkidle"),
    page.locator('input[name="_save"]').first().click(),
  ]);
}

// Layout checks deliberately use the same nine-digit amount and long Persian
// title across every desktop width. Keep a note of the seeded demo values and
// restore them after the full browser file finishes.
test.beforeAll(async ({ browser }, testInfo) => {
  if (!USER || !PASSWORD || testInfo.project.name !== "chromium") return;
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    locale: "fa-IR",
    timezoneId: "Asia/Tehran",
  });
  const page = await context.newPage();
  try {
    await login(page);
    const href = await firstProductWithVariantsUrl(page);
    await page.goto(new URL(href, BASE_URL).href, { waitUntil: "networkidle" });
    productLayoutFixtureOriginal = {
      name: await page.locator("#id_name").inputValue(),
      price: await page.locator("#id_price").inputValue(),
      compareAt: await page.locator("#id_compare_at_price").inputValue(),
    };
    await page.locator("#id_name").fill(LAYOUT_FIXTURE_NAME);
    await page.locator("#id_price").fill("123456789");
    await page.locator("#id_compare_at_price").fill("223456789");
    await Promise.all([
      page.waitForLoadState("networkidle"),
      page.locator('input[name="_save"]').first().click(),
    ]);
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }, testInfo) => {
  if (!productLayoutFixtureOriginal || testInfo.project.name !== "chromium") return;
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    locale: "fa-IR",
    timezoneId: "Asia/Tehran",
  });
  const page = await context.newPage();
  try {
    await login(page);
    await saveProductLayoutFixture(page, productLayoutFixtureOriginal);
  } finally {
    await context.close();
  }
});

async function assertNoHorizontalOverflow(page) {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(scrollWidth, `scrollWidth ${scrollWidth} vs clientWidth ${clientWidth}`).toBeLessThanOrEqual(clientWidth);
}

async function assertNineDigitNumericInputs(page, listPath, inputSelector) {
  await page.goto(`${BASE_URL}${listPath}`, { waitUntil: "networkidle" });
  const inputs = page.locator(inputSelector);
  const count = await inputs.count();
  expect(count, `${listPath} should render list_editable numeric inputs`).toBeGreaterThan(0);
  await inputs.evaluateAll((elements) => {
    for (const input of elements) {
      input.value = "123456789";
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
  const metrics = await inputs.evaluateAll((elements) => elements.map((input) => {
    const style = getComputedStyle(input);
    const rect = input.getBoundingClientRect();
    const sample = document.createElement("span");
    Object.assign(sample.style, {
      position: "fixed",
      left: "-10000px",
      width: "max-content",
      whiteSpace: "pre",
      fontFamily: style.fontFamily,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      fontStyle: style.fontStyle,
      fontVariantNumeric: style.fontVariantNumeric,
      fontFeatureSettings: style.fontFeatureSettings,
      letterSpacing: style.letterSpacing,
    });
    sample.textContent = input.value;
    document.body.appendChild(sample);
    const textWidth = sample.getBoundingClientRect().width;
    sample.remove();
    const horizontalChrome =
      parseFloat(style.paddingLeft) + parseFloat(style.paddingRight) +
      parseFloat(style.borderLeftWidth) + parseFloat(style.borderRightWidth) + 14;
    return {
      value: input.value,
      width: rect.width,
      usableTextWidth: rect.width - horizontalChrome,
      textWidth,
      dir: input.getAttribute("dir"),
      inputMode: input.getAttribute("inputmode"),
      direction: style.direction,
      fontVariantNumeric: style.fontVariantNumeric,
    };
  }));
  for (const input of metrics) {
    expect(input.value, `nine-digit value should remain intact: ${JSON.stringify(input)}`).toBe("123456789");
    expect(input.dir).toBe("ltr");
    expect(input.inputMode).toBe("numeric");
    expect(input.direction).toBe("ltr");
    expect(input.fontVariantNumeric).toContain("tabular-nums");
    expect(input.textWidth, `digits should fit outside the spinner: ${JSON.stringify(input)}`)
      .toBeLessThanOrEqual(input.usableTextWidth + 0.5);
  }
}

async function assertChangelistTextBreaksAtWords(page, pagePath) {
  await page.goto(`${BASE_URL}${pagePath}`, { waitUntil: "networkidle" });
  const textRuns = await page.locator("#result_list").evaluate((table) => {
    const walker = document.createTreeWalker(table, NodeFilter.SHOW_TEXT);
    const runs = [];
    let node;
    while ((node = walker.nextNode())) {
      const value = node.nodeValue.trim().replace(/\s+/gu, " ");
      if (!value) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      const tops = [];
      for (const rect of range.getClientRects()) {
        if (rect.width <= 0 || rect.height <= 0) continue;
        if (!tops.some((top) => Math.abs(top - rect.top) < 1)) tops.push(rect.top);
      }
      const cell = node.parentElement && node.parentElement.closest("th, td");
      runs.push({
        text: value,
        wordCount: value.split(/\s+/u).filter(Boolean).length,
        lineTops: tops.sort((a, b) => a - b),
        cell: cell ? cell.className : "outside-cell",
      });
    }
    return runs;
  });
  expect(textRuns.length, `${pagePath} should expose visible changelist text`).toBeGreaterThan(0);
  for (const run of textRuns) {
    expect(
      run.lineTops.length,
      `${pagePath} text must not split inside a word: ${JSON.stringify(run)}`
    ).toBeLessThanOrEqual(run.wordCount);
  }
}

async function assertProductRowItemsDoNotOverlap(page) {
  await page.goto(`${BASE_URL}/admin/products/product/`, { waitUntil: "networkidle" });
  await assertNoHorizontalOverflow(page);
  const rows = await page.locator("#result_list tbody tr").evaluateAll((elements) => {
    const isVisible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
    };
    const box = (element) => {
      const rect = element.getBoundingClientRect();
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
    };
    const overlaps = (a, b) =>
      Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0.75 &&
      Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0.75;
    const targets = "a, button, input, select, textarea, img, .cusin-badge, .cusin-thumb-empty";
    return elements.filter((row) => !row.classList.contains("add-row") && row.children.length)
      .map((row) => {
        const cells = [...row.children].filter(isVisible);
        const cellBoxes = cells.map((cell) => ({ element: cell, box: box(cell) }));
        const cellOverlaps = [];
        for (let i = 0; i < cellBoxes.length; i += 1) {
          for (let j = i + 1; j < cellBoxes.length; j += 1) {
            if (overlaps(cellBoxes[i].box, cellBoxes[j].box)) {
              cellOverlaps.push({ leftCell: cellBoxes[i].element.className, rightCell: cellBoxes[j].element.className });
            }
          }
        }
        const content = [...row.querySelectorAll(targets)].filter(isVisible).map((element) => {
          const rect = box(element);
          const cell = element.closest("td, th");
          const cellRect = cell.getBoundingClientRect();
          const cellStyle = getComputedStyle(cell);
          const inner = {
            left: cellRect.left + parseFloat(cellStyle.borderLeftWidth) + parseFloat(cellStyle.paddingLeft),
            right: cellRect.right - parseFloat(cellStyle.borderRightWidth) - parseFloat(cellStyle.paddingRight),
            top: cellRect.top + parseFloat(cellStyle.borderTopWidth) + parseFloat(cellStyle.paddingTop),
            bottom: cellRect.bottom - parseFloat(cellStyle.borderBottomWidth) - parseFloat(cellStyle.paddingBottom),
          };
          return {
            element,
            rect,
            inner,
            className: element.className || element.type || element.tagName,
            cellClass: cell.className,
          };
        });
        const outOfCell = content.filter(({ rect, inner }) =>
          rect.left < inner.left - 1 || rect.right > inner.right + 1 ||
          rect.top < inner.top - 1 || rect.bottom > inner.bottom + 1
        ).map(({ className, cellClass, rect, inner }) => ({ className, cellClass, rect, inner }));
        const topLevelContent = content.filter(({ element }) => {
          const parent = element.parentElement && element.parentElement.closest(targets);
          return !parent || parent.closest("tr") !== row;
        });
        const itemOverlaps = [];
        for (let i = 0; i < topLevelContent.length; i += 1) {
          for (let j = i + 1; j < topLevelContent.length; j += 1) {
            if (overlaps(topLevelContent[i].rect, topLevelContent[j].rect)) {
              itemOverlaps.push({
                first: topLevelContent[i].className,
                second: topLevelContent[j].className,
                firstCell: topLevelContent[i].cellClass,
                secondCell: topLevelContent[j].cellClass,
              });
            }
          }
        }
        const badge = row.querySelector("td.field-stock_quantity .stock-low");
        const stockInput = row.querySelector("td.field-stock_quantity input");
        return {
          cellOverlaps,
          outOfCell,
          itemOverlaps,
          lowStockOverlap: badge && stockInput ? overlaps(box(badge), box(stockInput)) : false,
        };
      });
  });
  expect(rows.length, "product changelist should include rows to inspect").toBeGreaterThan(0);
  for (const row of rows) {
    expect(row.cellOverlaps, `table cells overlap: ${JSON.stringify(row)}`).toEqual([]);
    expect(row.outOfCell, `row content escapes its cell: ${JSON.stringify(row)}`).toEqual([]);
    expect(row.itemOverlaps, `visible row elements overlap: ${JSON.stringify(row)}`).toEqual([]);
    expect(row.lowStockOverlap, `low-stock badge overlaps stock input: ${JSON.stringify(row)}`).toBe(false);
  }
}

async function assertProductHeaderWrapping(page) {
  const headers = await page.locator("#result_list thead tr:first-child > th").evaluateAll((cells) =>
    cells.map((cell) => {
      const text = cell.innerText.trim().replace(/\s+/g, " ");
      const textNodes = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
      const textRects = [];
      let node;
      while ((node = textNodes.nextNode())) {
        if (!node.nodeValue.trim()) continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        for (const rect of range.getClientRects()) {
          if (rect.width > 0 && rect.height > 0) {
            textRects.push({ left: rect.left, right: rect.right, top: rect.top });
          }
        }
      }
      const lines = textRects.map((rect) => rect.top).sort((a, b) => a - b).reduce((unique, top) => {
        if (!unique.some((existing) => Math.abs(existing - top) < 1)) unique.push(top);
        return unique;
      }, []);
      const cellRect = cell.getBoundingClientRect();
      const style = getComputedStyle(cell);
      return {
        text,
        wordCount: text ? text.split(/\s+/).length : 0,
        lineCount: lines.length,
        textRects,
        cell: { left: cellRect.left, right: cellRect.right },
        overflowWrap: style.overflowWrap,
        wordBreak: style.wordBreak,
        hyphens: style.hyphens,
      };
    })
  );
  for (const header of headers.filter((item) => item.wordCount > 0)) {
    expect(header.lineCount, `header should use at most two lines: ${JSON.stringify(header)}`).toBeLessThanOrEqual(2);
    expect(header.lineCount, `header must break only between words: ${JSON.stringify(header)}`).toBeLessThanOrEqual(header.wordCount);
    expect(header.overflowWrap).toBe("normal");
    expect(header.wordBreak).toBe("normal");
    expect(header.hyphens).toBe("none");
    for (const rect of header.textRects) {
      expect(rect.left, `header text should remain inside its cell: ${JSON.stringify(header)}`).toBeGreaterThanOrEqual(header.cell.left - 0.5);
      expect(rect.right, `header text should remain inside its cell: ${JSON.stringify(header)}`).toBeLessThanOrEqual(header.cell.right + 0.5);
    }
  }
}

async function assertDesktopChangelistLayout(page, pagePath) {
  const metrics = await page.evaluate(() => {
    const wrapper = document.querySelector("#changelist .results");
    const table = wrapper && wrapper.querySelector("#result_list");
    if (!wrapper || !table) return null;
    const box = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        left: rect.left,
        right: rect.right,
        width: rect.width,
        display: style.display,
        visible: rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden",
      };
    };
    const headers = [...table.querySelectorAll("thead tr:first-child > th")].map((cell) => ({
      ...box(cell),
      className: cell.className,
      text: cell.innerText.trim().replace(/\s+/g, " "),
    }));
    const rows = [...table.querySelectorAll("tbody tr")].map((row) => {
      const actionCell = row.querySelector("td.cusin-row-actions");
      return {
        cells: [...row.children].map(box),
        actions: actionCell ? {
          cell: box(actionCell),
          controls: [...actionCell.querySelectorAll(".cusin-row-edit, .cusin-row-more")].map(box),
        } : null,
      };
    });
    const name = table.querySelector("tbody .field-product_summary .cusin-product-summary__name");
    const nameStyle = name && getComputedStyle(name);
    const numericInputs = [...table.querySelectorAll(
      "tbody td.field-price input, tbody td.field-compare_at_price input, tbody td.field-stock_quantity input"
    )].map((input) => {
      const style = getComputedStyle(input);
      return {
        width: input.getBoundingClientRect().width,
        minWidth: style.minWidth,
        dir: input.getAttribute("dir"),
        inputMode: input.getAttribute("inputmode"),
        direction: style.direction,
        fontVariantNumeric: style.fontVariantNumeric,
      };
    });
    const orderNumbers = [...table.querySelectorAll(
      "tbody .field-order_number_cell .cusin-order-number"
    )].map((element) => ({
      text: element.textContent.trim(),
      title: element.getAttribute("title"),
      dir: element.getAttribute("dir"),
      direction: getComputedStyle(element).direction,
      whiteSpace: getComputedStyle(element).whiteSpace,
      fontFamily: getComputedStyle(element).fontFamily,
    }));
    const orderAmounts = [...table.querySelectorAll(
      "tbody .field-total_fa .cusin-order-amount"
    )].map((element) => ({
      text: element.textContent.trim(),
      title: element.getAttribute("title"),
      whiteSpace: getComputedStyle(element).whiteSpace,
    }));
    const wrapperBox = box(wrapper);
    return {
      wrapper: {
        ...wrapperBox,
        clientWidth: wrapper.clientWidth,
        scrollWidth: wrapper.scrollWidth,
        overflowX: getComputedStyle(wrapper).overflowX,
      },
      table: { ...box(table), layout: getComputedStyle(table).tableLayout },
      headers,
      rows,
      viewportWidth: window.innerWidth,
      orderNumbers,
      orderAmounts,
      productName: name && {
        lineClamp: nameStyle.webkitLineClamp,
        lineHeight: parseFloat(nameStyle.lineHeight),
        height: name.getBoundingClientRect().height,
      },
      numericInputs,
    };
  });

  expect(metrics, `${pagePath} should render a changelist table`).not.toBeNull();
  expect(metrics.table.visible, `${pagePath} table should be visible`).toBe(true);
  expect(metrics.table.layout, `${pagePath} desktop table should use fixed columns`).toBe("fixed");
  expect(metrics.table.width, `${pagePath} table should fit the results box`).toBeLessThanOrEqual(metrics.wrapper.clientWidth + 1);
  expect(metrics.wrapper.scrollWidth, `${pagePath} should not need a horizontal scrollbar at desktop width`).toBeLessThanOrEqual(metrics.wrapper.clientWidth + 1);
  expect(metrics.rows.length, `${pagePath} needs a sample row to measure`).toBeGreaterThan(0);

  const visibleHeaders = metrics.headers.filter((header) =>
    header.visible && !header.className.includes("storefront_data")
  );
  for (const header of visibleHeaders) {
    expect(header.visible, `${pagePath} column should be visible: ${JSON.stringify(header)}`).toBe(true);
    expect(header.left, `${pagePath} column should remain inside the results box`).toBeGreaterThanOrEqual(metrics.wrapper.left - 0.5);
    expect(header.right, `${pagePath} column should remain inside the results box`).toBeLessThanOrEqual(metrics.wrapper.right + 0.5);
  }
  const actionHeader = metrics.headers.find((header) => header.className.includes("column-cusin-row-actions"));
  expect(actionHeader?.text, `${pagePath} should keep the actions heading`).toBe("کارها");

  for (const row of metrics.rows) {
    expect(row.cells.length, `${pagePath} header/data column count`).toBe(metrics.headers.length);
    expect(row.actions, `${pagePath} row should keep its edit/menu actions`).not.toBeNull();
    expect(row.actions.cell.visible, `${pagePath} action cell should be visible`).toBe(true);
    expect(row.actions.cell.left).toBeGreaterThanOrEqual(metrics.wrapper.left - 0.5);
    expect(row.actions.cell.right).toBeLessThanOrEqual(metrics.wrapper.right + 0.5);
    expect(row.actions.controls.length, `${pagePath} should expose edit and more actions`).toBe(2);
    for (const control of row.actions.controls) {
      expect(control.visible, `${pagePath} row action should be visible: ${JSON.stringify(control)}`).toBe(true);
      expect(control.left).toBeGreaterThanOrEqual(row.actions.cell.left - 0.5);
      expect(control.right).toBeLessThanOrEqual(row.actions.cell.right + 0.5);
    }
    row.cells.forEach((cell, index) => {
      expect(Math.abs(cell.width - metrics.headers[index].width),
        `${pagePath} header/body column ${index} should align`).toBeLessThanOrEqual(2);
    });
  }

  if (pagePath === "/admin/orders/order/") {
    const orderNumberHeader = metrics.headers.find((header) => header.className.includes("column-order_number_cell"));
    const amountHeader = metrics.headers.find((header) => header.className.includes("column-total_fa"));
    expect(orderNumberHeader?.text).toBe("شماره");
    expect(amountHeader?.text).toBe("مبلغ (تومان)");
    expect(metrics.orderNumbers.length, "orders should render their LTR order number").toBeGreaterThan(0);
    for (const number of metrics.orderNumbers) {
      expect(number.dir).toBe("ltr");
      expect(number.direction).toBe("ltr");
      expect(number.whiteSpace).toBe("nowrap");
      expect(number.fontFamily).toContain("monospace");
      expect(number.title).toBe(number.text);
    }
    expect(metrics.orderAmounts.length, "orders should render their amounts").toBeGreaterThan(0);
    for (const amount of metrics.orderAmounts) {
      expect(amount.whiteSpace).toBe("nowrap");
      expect(amount.text).not.toContain("تومان");
      expect(amount.title).toBeTruthy();
    }
    for (const column of ["shipping_method_cell", "stock_restored_badge", "refund_badge", "created_at_jalali"]) {
      const header = metrics.headers.find((item) => item.className.includes(`column-${column}`));
      expect(header, `order ${column} header should exist`).toBeTruthy();
      expect(header.visible, `order ${column} visibility below 1440px`).toBe(metrics.viewportWidth >= 1440);
    }
  }

  if (pagePath === "/admin/products/product/") {
    expect(metrics.numericInputs.length, "product changelist should expose every editable numeric field").toBeGreaterThanOrEqual(3);
    for (const input of metrics.numericInputs) {
      expect(input.width, `product numeric input should fit nine digits: ${JSON.stringify(input)}`).toBeGreaterThanOrEqual(108);
      expect(input.width, `product numeric input should stay in its reserved column: ${JSON.stringify(input)}`).toBeLessThanOrEqual(120);
      expect(input.minWidth).toBe("108px");
      expect(input.dir).toBe("ltr");
      expect(input.inputMode).toBe("numeric");
      expect(input.direction).toBe("ltr");
      expect(input.fontVariantNumeric).toContain("tabular-nums");
    }
    expect(metrics.productName.lineClamp).toBe("2");
    expect(metrics.productName.height).toBeLessThanOrEqual(metrics.productName.lineHeight * 2 + 1);

    const headings = metrics.headers.map((header) => header.text);
    expect(headings).toContain("محصول");
    expect(headings).toContain("موجودی");
    expect(headings).toContain("فعال");
    expect(headings).toContain("ویژه");
    expect(headings).toContain("قیمت (تومان)");
    expect(headings).toContain("قیمت قبل از تخفیف");
    expect(headings).not.toContain("SKU");
  }
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
    const badges = [...document.querySelectorAll("#container .cusin-badge")]
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return element.innerText.trim() && rect.width > 0 && rect.height > 0 &&
          style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0";
      })
      .map((element) => ({ text: element.innerText.trim().slice(0, 40), size: getComputedStyle(element).fontSize }));
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
      badges,
      tightPersian,
    };
  });
  expect(metrics.bodySize, "admin desktop base text should be 16px").toBe(16);
  expect(metrics.bodyLineHeight, "Persian body leading should be at least 1.7").toBeGreaterThanOrEqual(1.7);
  expect(metrics.small, "visible admin text below 14px").toEqual([]);
  expect(metrics.badges.filter((badge) => parseFloat(badge.size) < 14), "visible admin status pills, including order status, must be at least 14px").toEqual([]);
  expect(metrics.tightPersian, "Persian text with line-height below 1.7").toEqual([]);
}

async function assertFormLayout(page, viewportWidth) {
  const formMetrics = await page.evaluate(() => {
    const visible = (element) => {
      const box = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return box.width > 0 && box.height > 0 && style.display !== "none" && style.visibility !== "hidden";
    };
    const textareas = [...document.querySelectorAll("#content-main textarea")]
      .filter(visible)
      .map((element) => {
        const box = element.getBoundingClientRect();
        const row = element.closest(".form-row");
        const rowBox = row.getBoundingClientRect();
        const lineHeight = parseFloat(getComputedStyle(element).lineHeight);
        return {
          width: box.width,
          rowWidth: rowBox.width,
          height: box.height,
          lineHeight,
          rows: Number.isFinite(lineHeight) ? box.height / lineHeight : 0,
        };
      });
    const help = [...document.querySelectorAll("#content-main .help, #content-main .helptext, #content-main .help-text")]
      .filter((element) => element.tagName !== "IMG" && element.textContent.trim() && visible(element))
      .map((element) => element.getBoundingClientRect().width);
    const controls = [...document.querySelectorAll(
      '#content-main fieldset.module.aligned .form-row input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="submit"]), ' +
      "#content-main fieldset.module.aligned .form-row select:not(.select2-hidden-accessible), #content-main fieldset.module.aligned .form-row textarea, " +
      "#content-main fieldset.module.aligned .form-row .related-widget-wrapper .select2-container, " +
      "#content-main fieldset.module.aligned .form-row .readonly"
    )]
      .filter((element) => visible(element) && !element.closest(".selector") && !element.classList.contains("select2-search__field"))
      .map((element) => ({
        tag: element.tagName,
        width: element.getBoundingClientRect().width,
        rowWidth: element.closest(".form-row").getBoundingClientRect().width,
      }));
    const fieldsets = [...document.querySelectorAll("#content-main fieldset.module.aligned")]
      .map((element) => getComputedStyle(element).display);
    return { textareas, help, controls, fieldsets };
  });

  expect(formMetrics.textareas.length, "change form should expose its textareas").toBeGreaterThan(0);
  for (const textarea of formMetrics.textareas) {
    expect(textarea.rows, `textarea should render at least six lines: ${JSON.stringify(textarea)}`).toBeGreaterThanOrEqual(6);
    if (viewportWidth === 375) {
      expect(textarea.width, `phone textarea should fill its column: ${JSON.stringify(textarea)}`).toBeGreaterThanOrEqual(textarea.rowWidth * 0.9);
    } else if (viewportWidth >= 1280) {
      expect(textarea.width, `desktop textarea should be at least 480px: ${JSON.stringify(textarea)}`).toBeGreaterThanOrEqual(480);
    }
  }
  expect(formMetrics.controls.length, "change form should expose controls").toBeGreaterThan(0);
  for (const control of formMetrics.controls) {
    if (viewportWidth === 375) {
      expect(control.width, `phone control should fill its column: ${JSON.stringify(control)}`).toBeGreaterThanOrEqual(control.rowWidth * 0.9);
    } else if (viewportWidth >= 1280) {
      expect(control.width, `desktop control should fill its column: ${JSON.stringify(control)}`).toBeGreaterThanOrEqual(control.rowWidth * 0.85);
    }
  }
  for (const width of formMetrics.help) {
    if (viewportWidth === 375 || viewportWidth >= 1280) {
      expect(width, `help text should retain a readable column at ${viewportWidth}px`).toBeGreaterThanOrEqual(200);
    }
  }
  for (const display of formMetrics.fieldsets) {
    expect(display, `fieldset layout at ${viewportWidth}px`).toBe(viewportWidth < 1024 ? "block" : "grid");
  }
}

async function assertSelectorFormLayout(page, viewportWidth) {
  const widgets = await page.locator("#content-main fieldset.module.aligned .form-row .selector").evaluateAll((elements) =>
    elements.map((element) => {
      const row = element.closest(".form-row");
      const available = element.querySelector(".selector-available");
      const chosen = element.querySelector(".selector-chosen");
      const help = [...element.querySelectorAll(".helptext")].map((item) => item.getBoundingClientRect().width);
      return {
        rowWidth: row.getBoundingClientRect().width,
        widgetWidth: element.getBoundingClientRect().width,
        direction: getComputedStyle(element).flexDirection,
        panelWidths: [available, chosen].filter(Boolean).map((panel) => panel.getBoundingClientRect().width),
        help,
      };
    })
  );
  expect(widgets.length, "the model form should expose a dual-list selector").toBeGreaterThan(0);
  for (const widget of widgets) {
    expect(widget.widgetWidth, `selector should fill its row: ${JSON.stringify(widget)}`).toBeGreaterThanOrEqual(widget.rowWidth * 0.9);
    if (viewportWidth >= 1280) {
      expect(widget.rowWidth, `desktop selector should span both form columns: ${JSON.stringify(widget)}`).toBeGreaterThanOrEqual(700);
    }
    if (viewportWidth === 375) {
      expect(widget.direction, "phone dual-list controls should stack").toBe("column");
      for (const panelWidth of widget.panelWidths) {
        expect(panelWidth, `phone selector panel should retain readable width: ${JSON.stringify(widget)}`).toBeGreaterThanOrEqual(240);
      }
    }
    for (const helpWidth of widget.help) {
      expect(helpWidth, `dual-list help should be at least 200px wide: ${JSON.stringify(widget)}`).toBeGreaterThanOrEqual(200);
    }
  }
}

async function assertInlineFormLayout(page, viewportWidth, includesGallery = false) {
  const metrics = await page.evaluate(() => {
    const visible = (element) => {
      const box = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return box.width > 0 && box.height > 0 && style.display !== "none" && style.visibility !== "hidden";
    };
    const tables = [...document.querySelectorAll("#content-main .inline-group .tabular")]
      .filter(visible)
      .map((wrapper) => {
        const table = wrapper.querySelector("table");
        const group = wrapper.closest(".inline-group");
        const rows = [...wrapper.querySelectorAll("tbody tr.form-row:not(.empty-form):not(.add-row)")]
          .filter(visible);
        const rect = wrapper.getBoundingClientRect();
        const groupRect = group.getBoundingClientRect();
        return {
          overflowX: getComputedStyle(wrapper).overflowX,
          wrapper: { left: rect.left, right: rect.right, width: rect.width, clientWidth: wrapper.clientWidth, scrollWidth: wrapper.scrollWidth },
          group: { left: groupRect.left, right: groupRect.right, width: groupRect.width },
          tableWidth: table.getBoundingClientRect().width,
          rows: rows.map((row) => {
            const rowRect = row.getBoundingClientRect();
            return {
              display: getComputedStyle(row).display,
              height: rowRect.height,
              bounds: { left: rowRect.left, right: rowRect.right },
              cells: [...row.children].map((cell) => {
                const cellRect = cell.getBoundingClientRect();
                return {
                  width: cellRect.width,
                  display: getComputedStyle(cell).display,
                  label: cell.getAttribute("data-label"),
                  cls: cell.className,
                  hidden: getComputedStyle(cell).display === "none",
                };
              }),
            };
          }),
          headers: [...table.querySelectorAll("thead th")].map((cell) => cell.getBoundingClientRect().width),
        };
      });
    const gallery = document.querySelector("#content-main .cusin-gallery");
    const cards = gallery ? [...gallery.querySelectorAll(".cusin-gallery-card:not(.empty-form)")].filter(visible) : [];
    const galleryRect = gallery ? gallery.getBoundingClientRect() : null;
    const galleryMetrics = gallery ? {
      display: getComputedStyle(gallery).display,
      columns: getComputedStyle(gallery).gridTemplateColumns,
      width: galleryRect.width,
      cards: cards.map((card) => {
        const rect = card.getBoundingClientRect();
        return { left: rect.left, right: rect.right, width: rect.width };
      }),
    } : null;
    return {
      pageWidth: document.documentElement.clientWidth,
      pageScrollWidth: document.documentElement.scrollWidth,
      tables,
      gallery: galleryMetrics,
    };
  });

  expect(metrics.tables.length, "the form should render its TabularInline scroller").toBeGreaterThan(0);
  expect(metrics.pageScrollWidth, "inline tables must not widen the page").toBeLessThanOrEqual(metrics.pageWidth);
  for (const table of metrics.tables) {
    expect(table.overflowX, "inline table wrapper should own horizontal overflow").toBe("auto");
    expect(table.wrapper.left, "inline scroller should stay inside its card").toBeGreaterThanOrEqual(table.group.left - 0.5);
    expect(table.wrapper.right, "inline scroller should stay inside its card").toBeLessThanOrEqual(table.group.right + 0.5);
    expect(table.rows.length, "seeded inline should render a row").toBeGreaterThan(0);
    if (viewportWidth >= 1280) {
      expect(table.headers.length, "header and data rows should share their column count").toBe(table.rows[0].cells.length);
      if (table.tableWidth > table.wrapper.clientWidth + 4) {
        expect(table.wrapper.scrollWidth, "wide inline tables should scroll inside their own box").toBeGreaterThan(table.wrapper.clientWidth + 4);
      }
      for (const row of table.rows) {
        expect(row.display, "desktop rows should retain table-row alignment").toBe("table-row");
        expect(row.height, `desktop inline row should not become tall: ${JSON.stringify(row)}`).toBeLessThanOrEqual(180);
        expect(table.headers.length, "header and data rows should share their column count").toBe(row.cells.length);
        table.headers.forEach((width, index) => {
          expect(Math.abs(width - row.cells[index].width), `header/data column ${index} should align: ${JSON.stringify(row)}`).toBeLessThanOrEqual(2);
        });
      }
    } else if (viewportWidth === 375) {
      for (const row of table.rows) {
        expect(row.display, "phone inline rows should become cards").toBe("grid");
        expect(row.height, `phone inline card should remain compact: ${JSON.stringify(row)}`).toBeLessThanOrEqual(600);
        expect(row.bounds.left, "phone inline card left edge").toBeGreaterThanOrEqual(0);
        expect(row.bounds.right, "phone inline card right edge").toBeLessThanOrEqual(metrics.pageWidth + 0.5);
        for (const cell of row.cells.filter((item) => !item.hidden && !/\boriginal\b|\bhidden\b/.test(item.cls))) {
          expect(cell.display, `phone inline data cells should stack: ${JSON.stringify(cell)}`).toBe("grid");
          expect(cell.label, `phone inline cell should have a mirrored header label: ${JSON.stringify(cell)}`).toBeTruthy();
        }
      }
    }
  }

  if (includesGallery) {
    expect(metrics.gallery, "product image gallery should stay as cards").not.toBeNull();
    expect(metrics.gallery.display).toBe("grid");
    expect(metrics.gallery.cards.length).toBeGreaterThan(0);
    for (const card of metrics.gallery.cards) {
      expect(card.width, `gallery card width: ${JSON.stringify(card)}`).toBeLessThanOrEqual(metrics.gallery.width + 0.5);
      expect(card.left).toBeGreaterThanOrEqual(0);
      expect(card.right).toBeLessThanOrEqual(metrics.pageWidth + 0.5);
    }
    if (viewportWidth === 375) {
      expect(metrics.gallery.columns.trim().split(/\s+/).length, "phone image cards should use one column").toBe(1);
    }
  }
}

async function assertInlineCellContentIsContained(page, viewportWidth, includesGallery = false, includesPayments = false) {
  const metrics = await page.evaluate(() => {
    const visible = (element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.display !== "none" &&
        style.visibility !== "hidden" && style.opacity !== "0";
    };
    const box = (element) => {
      const rect = element.getBoundingClientRect();
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
    };
    const intersects = (a, b) =>
      Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0.75 &&
      Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0.75;
    const describeRow = (row) => {
      const cells = [...row.children].map((cell, cellIndex) => {
        const rect = cell.getBoundingClientRect();
        const style = getComputedStyle(cell);
        const inner = {
          left: rect.left + parseFloat(style.borderLeftWidth) + parseFloat(style.paddingLeft),
          right: rect.right - parseFloat(style.borderRightWidth) - parseFloat(style.paddingRight),
          top: rect.top + parseFloat(style.borderTopWidth) + parseFloat(style.paddingTop),
          bottom: rect.bottom - parseFloat(style.borderBottomWidth) - parseFloat(style.paddingBottom),
        };
        const contents = [...cell.children].filter(visible).map((element) => ({
          rect: box(element),
          inner,
          cellIndex,
          cellClass: cell.className,
          className: element.className || element.type || element.tagName,
        }));
        return {
          cell,
          cellIndex,
          rect: box(cell),
          className: cell.className,
          hidden: getComputedStyle(cell).display === "none",
          contents,
        };
      });
      const visibleCells = cells.filter(({ hidden }) => !hidden);
      const cellOverlaps = [];
      for (let i = 0; i < visibleCells.length; i += 1) {
        for (let j = i + 1; j < visibleCells.length; j += 1) {
          if (intersects(visibleCells[i].rect, visibleCells[j].rect)) {
            cellOverlaps.push({ first: visibleCells[i].className, second: visibleCells[j].className });
          }
        }
      }
      const content = cells.flatMap(({ contents }) => contents);
      const outOfCell = content.filter(({ rect, inner }) =>
        rect.left < inner.left - 1 || rect.right > inner.right + 1 ||
        rect.top < inner.top - 1 || rect.bottom > inner.bottom + 1
      ).map(({ className, cellClass, rect, inner }) => ({ className, cellClass, rect, inner }));
      const contentOverlaps = [];
      for (let i = 0; i < content.length; i += 1) {
        for (let j = i + 1; j < content.length; j += 1) {
          if (content[i].cellIndex !== content[j].cellIndex && intersects(content[i].rect, content[j].rect)) {
            contentOverlaps.push({
              first: content[i].className,
              second: content[j].className,
              firstCell: content[i].cellClass,
              secondCell: content[j].cellClass,
            });
          }
        }
      }
      return {
        cellOverlaps,
        outOfCell,
        contentOverlaps,
        originalHidden: !row.querySelector("td.original") ||
          getComputedStyle(row.querySelector("td.original")).display === "none",
      };
    };
    const tables = [...document.querySelectorAll("#content-main .inline-group .tabular")]
      .filter(visible)
      .map((wrapper) => {
        const table = wrapper.querySelector("table");
        return {
          id: wrapper.closest(".inline-group").id,
          wrapperClientWidth: wrapper.clientWidth,
          wrapperScrollWidth: wrapper.scrollWidth,
          tableWidth: table.getBoundingClientRect().width,
          rows: [...table.querySelectorAll("tbody tr.form-row:not(.empty-form):not(.add-row)")]
            .filter(visible).map(describeRow),
        };
      });
    const gallery = document.querySelector("#content-main .cusin-gallery");
    const cards = gallery ? [...gallery.querySelectorAll(".cusin-gallery-card:not(.empty-form)")].filter(visible) : [];
    const galleryMetrics = gallery ? {
      clientWidth: gallery.clientWidth,
      scrollWidth: gallery.scrollWidth,
      cards: cards.map((card) => {
        const cardRect = card.getBoundingClientRect();
        const cardStyle = getComputedStyle(card);
        const inner = {
          left: cardRect.left + parseFloat(cardStyle.borderLeftWidth) + parseFloat(cardStyle.paddingLeft),
          right: cardRect.right - parseFloat(cardStyle.borderRightWidth) - parseFloat(cardStyle.paddingRight),
          top: cardRect.top + parseFloat(cardStyle.borderTopWidth) + parseFloat(cardStyle.paddingTop),
          bottom: cardRect.bottom - parseFloat(cardStyle.borderBottomWidth) - parseFloat(cardStyle.paddingBottom),
        };
        const children = [...card.children].filter(visible).map((element) => ({
          rect: box(element),
          className: element.className || element.tagName,
        }));
        const overlaps = [];
        for (let i = 0; i < children.length; i += 1) {
          for (let j = i + 1; j < children.length; j += 1) {
            if (intersects(children[i].rect, children[j].rect)) {
              overlaps.push({ first: children[i].className, second: children[j].className });
            }
          }
        }
        const outOfCard = children.filter(({ rect }) =>
          rect.left < inner.left - 1 || rect.right > inner.right + 1 ||
          rect.top < inner.top - 1 || rect.bottom > inner.bottom + 1
        ).map(({ className, rect }) => ({ className, rect, inner }));
        const controlsOutOfField = [...card.querySelectorAll(".cusin-gallery-field")].flatMap((field) => {
          const fieldRect = field.getBoundingClientRect();
          return [...field.querySelectorAll("input:not([type=hidden]), select, textarea")]
            .filter(visible)
            .filter((control) => {
              const rect = control.getBoundingClientRect();
              return rect.left < fieldRect.left - 1 || rect.right > fieldRect.right + 1 ||
                rect.top < fieldRect.top - 1 || rect.bottom > fieldRect.bottom + 1;
            }).map((control) => ({
              field: field.className,
              control: control.type || control.tagName,
              rect: box(control),
              fieldRect: box(field),
            }));
        });
        return {
          clientWidth: card.clientWidth,
          scrollWidth: card.scrollWidth,
          overlaps,
          outOfCard,
          controlsOutOfField,
        };
      }),
    } : null;
    const summaryTables = [
      ...document.querySelectorAll('section[aria-label="اقلام سفارش"] .cusin-table-scroll'),
      ...document.querySelectorAll('section[aria-label="پرداخت و بازپرداخت"] .cusin-table-scroll'),
    ].filter((wrapper) => visible(wrapper) && wrapper.querySelector("table"))
      .map((wrapper) => {
        const table = wrapper.querySelector("table");
        return {
          wrapperClientWidth: wrapper.clientWidth,
          wrapperScrollWidth: wrapper.scrollWidth,
          tableWidth: table.getBoundingClientRect().width,
          rows: [...table.querySelectorAll("tbody tr")].filter(visible).map(describeRow),
        };
      });
    return { tables, gallery: galleryMetrics, summaryTables };
  });

  expect(metrics.tables.length, "inline tables should be present for overlap inspection").toBeGreaterThan(0);
  for (const table of metrics.tables) {
    expect(table.rows.length).toBeGreaterThan(0);
    if (table.id === "variants-group" && viewportWidth >= 1280) {
      expect(table.tableWidth, "product variants table should fit its card").toBeLessThanOrEqual(table.wrapperClientWidth + 2);
      expect(table.wrapperScrollWidth, "product variants card should not need horizontal scrolling").toBeLessThanOrEqual(table.wrapperClientWidth + 4);
      expect(table.rows.length, "the selected product should have two saved variants").toBeGreaterThanOrEqual(2);
    }
    for (const row of table.rows) {
      expect(row.originalHidden, `Django original label must be hidden: ${JSON.stringify(row)}`).toBe(true);
      expect(row.cellOverlaps, `inline cells overlap: ${JSON.stringify(row)}`).toEqual([]);
      expect(row.outOfCell, `inline content escapes its cell: ${JSON.stringify(row)}`).toEqual([]);
      expect(row.contentOverlaps, `inline cell contents overlap: ${JSON.stringify(row)}`).toEqual([]);
    }
  }

  if (includesGallery) {
    expect(metrics.gallery, "product image gallery should stay as bounded cards").not.toBeNull();
    expect(metrics.gallery.cards.length).toBeGreaterThan(0);
    expect(metrics.gallery.scrollWidth).toBeLessThanOrEqual(metrics.gallery.clientWidth + 1);
    for (const card of metrics.gallery.cards) {
      expect(card.scrollWidth, `gallery card should not overflow: ${JSON.stringify(card)}`).toBeLessThanOrEqual(card.clientWidth + 1);
      expect(card.overlaps, `gallery card children overlap: ${JSON.stringify(card)}`).toEqual([]);
      expect(card.outOfCard, `gallery content escapes its card: ${JSON.stringify(card)}`).toEqual([]);
      expect(card.controlsOutOfField, `gallery control escapes its field: ${JSON.stringify(card)}`).toEqual([]);
    }
  }

  if (includesPayments) {
    expect(metrics.summaryTables.length, "order summary should include item and payment tables").toBeGreaterThanOrEqual(2);
    for (const table of metrics.summaryTables) {
      expect(table.rows.length, "order summary table should contain data").toBeGreaterThan(0);
      if (viewportWidth >= 1280) {
        expect(table.tableWidth, `desktop summary table should fit its card: ${JSON.stringify(table)}`).toBeLessThanOrEqual(table.wrapperClientWidth + 2);
        expect(table.wrapperScrollWidth, `desktop summary table should not scroll: ${JSON.stringify(table)}`).toBeLessThanOrEqual(table.wrapperClientWidth + 4);
      }
      for (const row of table.rows) {
        expect(row.cellOverlaps, `order summary cells overlap: ${JSON.stringify(row)}`).toEqual([]);
        expect(row.outOfCell, `order summary content escapes its cell: ${JSON.stringify(row)}`).toEqual([]);
        expect(row.contentOverlaps, `order summary cell contents overlap: ${JSON.stringify(row)}`).toEqual([]);
      }
    }
  }
}

async function assertHelpTextInsideFieldset(page) {
  const helps = await page.locator(".help").evaluateAll((elements) => elements.flatMap((element) => {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    if (rect.width <= 0 || rect.height <= 0 || style.display === "none" ||
        style.visibility === "hidden" || style.opacity === "0") return [];
    const fieldset = element.closest("fieldset");
    const fieldsetRect = fieldset && fieldset.getBoundingClientRect();
    return [{
      id: element.id,
      className: element.className,
      text: element.textContent.trim().replace(/\s+/g, " ").slice(0, 90),
      help: { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom },
      fieldset: fieldset ? {
        id: fieldset.id,
        className: fieldset.className,
        left: fieldsetRect.left,
        right: fieldsetRect.right,
        top: fieldsetRect.top,
        bottom: fieldsetRect.bottom,
      } : null,
      contained: Boolean(fieldset) && rect.left >= fieldsetRect.left - 1 &&
        rect.right <= fieldsetRect.right + 1 && rect.top >= fieldsetRect.top - 1 &&
        rect.bottom <= fieldsetRect.bottom + 1,
    }];
  }));
  expect(helps.length, "the tested form should render visible help text").toBeGreaterThan(0);
  expect(helps.filter((help) => !help.contained), "every visible .help must stay inside its fieldset").toEqual([]);
}

async function assertLatestOrdersLayout(page) {
  const viewportWidth = page.viewportSize().width;
  const section = page.locator('section[aria-label="آخرین سفارش‌ها"]');
  const metrics = await section.evaluate((card) => {
    const wrapper = card.querySelector(".cusin-orders-scroll");
    const table = wrapper && wrapper.querySelector(".cusin-orders-table");
    if (!wrapper || !table) return null;
    const cardRect = card.getBoundingClientRect();
    const wrapperRect = wrapper.getBoundingClientRect();
    const cardStyle = getComputedStyle(card);
    const rows = [...table.querySelectorAll("tbody tr")].map((row) => {
      const cell = row.querySelector("th.cusin-order-number");
      const cellStyle = getComputedStyle(cell);
      const anchor = cell.querySelector("a");
      const range = document.createRange();
      range.selectNodeContents(anchor);
      const lineRects = [...range.getClientRects()];
      const rowRect = row.getBoundingClientRect();
      const cells = [...row.children].map((orderCell) => {
        const cellRect = orderCell.getBoundingClientRect();
        const cellStyle = getComputedStyle(orderCell);
        const label = getComputedStyle(orderCell, "::before");
        return {
          label: orderCell.dataset.label || "",
          display: cellStyle.display,
          left: cellRect.left,
          right: cellRect.right,
          top: cellRect.top,
          bottom: cellRect.bottom,
          labelContent: label.content,
          labelFontSize: label.fontSize,
        };
      });
      return {
        text: cell.textContent.trim(),
        dirAttribute: cell.getAttribute("dir"),
        direction: cellStyle.direction,
        whiteSpace: getComputedStyle(anchor).whiteSpace,
        fontFamily: cellStyle.fontFamily,
        lineCount: lineRects.length,
        display: getComputedStyle(row).display,
        left: rowRect.left,
        right: rowRect.right,
        bottom: rowRect.bottom,
        cells,
      };
    });
    const headers = [...table.querySelectorAll("thead th")].map((header) => {
      const rect = header.getBoundingClientRect();
      return { text: header.textContent.trim(), display: getComputedStyle(header).display, width: rect.width, height: rect.height };
    });
    return {
      rows,
      headers,
      card: {
        clientHeight: card.clientHeight,
        scrollHeight: card.scrollHeight,
        bottom: cardRect.bottom,
        contentBottom: cardRect.bottom - parseFloat(cardStyle.paddingBottom) - parseFloat(cardStyle.borderBottomWidth),
        overflowY: cardStyle.overflowY,
        gridColumn: getComputedStyle(card).gridColumn,
      },
      wrapper: {
        left: wrapperRect.left,
        right: wrapperRect.right,
        cardLeft: cardRect.left,
        cardRight: cardRect.right,
        clientWidth: wrapper.clientWidth,
        scrollWidth: wrapper.scrollWidth,
        overflowX: getComputedStyle(wrapper).overflowX,
      },
      table: {
        width: table.getBoundingClientRect().width,
        clientWidth: table.clientWidth,
        scrollWidth: table.scrollWidth,
        display: getComputedStyle(table).display,
        bodyDisplay: getComputedStyle(table.querySelector("tbody")).display,
      },
    };
  });

  expect(metrics, "dashboard should render the latest-orders table").not.toBeNull();
  expect(metrics.rows.length, "dashboard should show its four latest orders").toBe(4);
  expect(metrics.headers).toHaveLength(5);
  expect(metrics.wrapper.left).toBeGreaterThanOrEqual(metrics.wrapper.cardLeft - 0.5);
  expect(metrics.wrapper.right).toBeLessThanOrEqual(metrics.wrapper.cardRight + 0.5);
  expect(metrics.card.scrollHeight, "latest-orders card must not clip vertical content").toBeLessThanOrEqual(metrics.card.clientHeight + 2);

  if (viewportWidth < 768) {
    const expectedLabels = ["شماره", "وضعیت", "پرداخت", "مبلغ", "تاریخ"];
    expect(metrics.wrapper.overflowX).toBe("visible");
    expect(metrics.table.display).toBe("block");
    expect(metrics.table.bodyDisplay).toBe("grid");
    expect(metrics.table.scrollWidth, "phone orders must not retain the wide table").toBeLessThanOrEqual(metrics.wrapper.clientWidth + 1);
    expect(metrics.wrapper.scrollWidth, "phone orders must not scroll horizontally").toBeLessThanOrEqual(metrics.wrapper.clientWidth + 1);
    for (const row of metrics.rows) {
      expect(row.display, "each phone order should be a stacked card").toBe("grid");
      expect(row.left).toBeGreaterThanOrEqual(metrics.wrapper.left - 0.5);
      expect(row.right).toBeLessThanOrEqual(metrics.wrapper.right + 0.5);
      expect(row.cells.map((cell) => cell.label)).toEqual(expectedLabels);
      for (let index = 0; index < row.cells.length; index += 1) {
        const cell = row.cells[index];
        expect(cell.display).toBe("grid");
        expect(cell.labelContent).toContain(cell.label);
        expect(parseFloat(cell.labelFontSize)).toBeGreaterThanOrEqual(14);
        if (index > 0) {
          expect(cell.top, "labeled phone order fields must not overlap").toBeGreaterThanOrEqual(row.cells[index - 1].bottom - 1);
        }
      }
    }
  } else {
    for (const row of metrics.rows) {
      expect(row.display).toBe("table-row");
      expect(row.cells).toHaveLength(5);
    }
    if (viewportWidth >= 1280) {
      expect(metrics.card.gridColumn).toBe("1 / -1");
      expect(metrics.wrapper.scrollWidth, "five desktop columns must fit without horizontal scrolling").toBeLessThanOrEqual(metrics.wrapper.clientWidth + 1);
      expect(metrics.table.scrollWidth).toBeLessThanOrEqual(metrics.wrapper.clientWidth + 1);
      expect(metrics.table.width).toBeLessThanOrEqual(metrics.wrapper.clientWidth + 1);
      for (const header of metrics.headers) {
        expect(header.display).not.toBe("none");
        expect(header.width).toBeGreaterThan(0);
        expect(header.height).toBeGreaterThan(0);
      }
    } else if (metrics.table.width > metrics.wrapper.clientWidth + 4) {
      expect(metrics.wrapper.scrollWidth, "narrow desktop table may scroll only inside its card").toBeGreaterThan(metrics.wrapper.clientWidth + 4);
    }
  }

  for (const row of metrics.rows) {
    expect(row.text).toMatch(/^[A-Za-z0-9-]+$/);
    expect(row.dirAttribute).toBe("ltr");
    expect(row.direction).toBe("ltr");
    expect(row.whiteSpace).toBe("nowrap");
    expect(row.fontFamily).toMatch(/monospace/i);
    expect(row.lineCount, `order number must stay on one line: ${JSON.stringify(row)}`).toBe(1);
    expect(row.bottom, "latest-orders card should grow to fit every row").toBeLessThanOrEqual(metrics.card.contentBottom + 1);
  }
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
          if (pagePath === "/admin/") await assertLatestOrdersLayout(page);
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
          await assertFormLayout(page, viewport.width);
        });
      }

      if (viewport.width === 375 || viewport.width === 1280 || viewport.width === 1440) {
        for (const form of [
          { label: "product variant", getUrl: firstProductVariantUrl },
          { label: "user", getUrl: firstUserUrl },
        ]) {
          test(`dual-list layout fills the ${form.label} form column`, async ({ page }) => {
            const url = await form.getUrl(page);
            await page.goto(new URL(url, BASE_URL).href, { waitUntil: "networkidle" });
            await assertNoHorizontalOverflow(page);
            await assertSelectorFormLayout(page, viewport.width);
          });
        }

        for (const form of [
          { label: "product variants and image gallery", getUrl: firstProductWithVariantsUrl, includesGallery: true, includesPayments: false },
          { label: "order items", getUrl: firstOrderUrl, includesGallery: false, includesPayments: true },
          { label: "cart items", getUrl: firstCartUrl, includesGallery: false, includesPayments: false },
        ]) {
          test(`inline rows are aligned and contained on ${form.label}`, async ({ page }) => {
            const url = await form.getUrl(page);
            await page.goto(new URL(url, BASE_URL).href, { waitUntil: "networkidle" });
            await assertNoHorizontalOverflow(page);
            await assertInlineFormLayout(page, viewport.width, form.includesGallery);
            await assertInlineCellContentIsContained(
              page,
              viewport.width,
              form.includesGallery,
              form.includesPayments,
            );
            if (form.includesGallery || form.includesPayments) {
              await assertHelpTextInsideFieldset(page);
            }
          });
        }

        if (viewport.width === 375) {
          test("a newly added product variant row receives its mobile column labels", async ({ page }) => {
            const url = await firstProductWithVariantsUrl(page);
            await page.goto(new URL(url, BASE_URL).href, { waitUntil: "networkidle" });
            const table = page.locator("#variants-group .tabular");
            const addAnother = table.locator(".add-row a");
            await expect(addAnother).toBeVisible();
            const rows = table.locator("tbody tr.form-row:not(.empty-form):not(.add-row)");
            const before = await rows.count();
            await addAnother.click();
            await expect(rows).toHaveCount(before + 1);
            const added = rows.last();
            await expect.poll(() => added.locator("td[data-label]").count()).toBeGreaterThan(2);
          });
        }
      }

      if (viewport.width >= 1280) {
        test("dashboard content fills the desktop column", async ({ page }) => {
          await page.goto(`${BASE_URL}/admin/`, { waitUntil: "networkidle" });
          const box = await page.locator("#content").boundingBox();
          expect(box, "#content must be rendered").not.toBeNull();
          expect(box.width).toBeGreaterThan(800);
        });

        for (const pagePath of CHANGELISTS) {
          test(`all columns and row actions fit on ${pagePath}`, async ({ page }) => {
            await page.goto(`${BASE_URL}${pagePath}`, { waitUntil: "networkidle" });
            await assertDesktopChangelistLayout(page, pagePath);
          });
        }

        if (viewport.width === 1280) {
          test("normal navigation and menu labels stay near-black; active and destructive items stay distinct", async ({ page }) => {
            await page.goto(`${BASE_URL}/admin/products/product/`, { waitUntil: "networkidle" });
            const sidebar = await page.evaluate(() => {
              const color = (selector) => getComputedStyle(document.querySelector(selector)).color;
              return {
                activeGroup: color("#cusin-drawer .cusin-nav-group.is-active > summary"),
                activeLink: color("#cusin-drawer .cusin-nav-link.is-active"),
                normalLink: color("#cusin-drawer .cusin-nav-group.is-active .cusin-nav-link:not(.is-active)"),
                normalDashboard: color("#cusin-drawer .cusin-drawer-dash:not(.is-active)"),
              };
            });
            expect(sidebar.activeGroup).toBe("rgb(17, 24, 39)");
            expect(sidebar.normalLink).toBe("rgb(17, 24, 39)");
            expect(sidebar.normalDashboard).toBe("rgb(17, 24, 39)");
            expect(sidebar.activeLink).toBe("rgb(79, 90, 44)");

            await page.locator("#result_list .cusin-row-more").first().click();
            const rowMenu = page.locator(".cusin-menu-panel:not([hidden])").last();
            await expect(rowMenu).toBeVisible();
            const rowLabel = rowMenu.locator(".cusin-menu-item:not(.is-danger)").last();
            const destructiveLabel = rowMenu.locator(".cusin-menu-item.is-danger").first();
            expect(await rowLabel.evaluate((el) => getComputedStyle(el).color)).toBe("rgb(17, 24, 39)");
            expect(await destructiveLabel.evaluate((el) => getComputedStyle(el).color)).toBe("rgb(143, 29, 20)");
            await page.keyboard.press("Escape");

            await page.locator("#cusin-user-menu-trigger").click();
            const userMenu = page.locator("#cusin-user-menu");
            await expect(userMenu).toBeVisible();
            const userLabel = userMenu.locator('[role="menuitem"]:not(.is-danger)').last();
            expect(await userLabel.evaluate((el) => getComputedStyle(el).color)).toBe("rgb(17, 24, 39)");
          });
        }
      }

      if (viewport.width === 1024) {
        for (const pagePath of CHANGELISTS) {
          test(`horizontal scrolling stays inside the ${pagePath} results box`, async ({ page }) => {
            await page.goto(`${BASE_URL}${pagePath}`, { waitUntil: "networkidle" });
            await assertNoHorizontalOverflow(page);
            const overflowX = await page.locator("#changelist .results").evaluate((el) => getComputedStyle(el).overflowX);
            expect(overflowX, `${pagePath} results should own tablet-width scrolling`).toBe("auto");
          });
        }
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

test.describe("changelist text breaks only between words", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only; this spec sets its own viewport");
    await login(page);
  });

  const wordSafeLists = [
    "/admin/products/product/",
    "/admin/orders/order/",
    "/admin/accounts/user/",
    "/admin/categories/category/",
    "/admin/discounts/coupon/",
  ];
  for (const width of [1024, 1280, 1440, 1920]) {
    test.describe(`${width}px`, () => {
      test.use({ viewport: { width, height: 1000 } });

      for (const pagePath of wordSafeLists) {
        test(`every text node stays within whole words on ${pagePath}`, async ({ page }) => {
          await assertChangelistTextBreaksAtWords(page, pagePath);
        });
      }
    });
  }
});

test.describe("SKU editor direction", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");
  test.use({ viewport: { width: 1280, height: 1000 } });

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only");
    await login(page);
  });

  test("product, inline-variant and standalone-variant SKU inputs are LTR", async ({ page }) => {
    const productUrl = await firstProductWithVariantsUrl(page);
    await page.goto(new URL(productUrl, BASE_URL).href, { waitUntil: "networkidle" });
    const productSku = page.locator("#id_sku");
    await expect(productSku).toHaveAttribute("dir", "ltr");
    expect(await productSku.evaluate((input) => getComputedStyle(input).direction)).toBe("ltr");

    const inlineSkus = page.locator('#variants-group input[name$="-sku"]');
    expect(await inlineSkus.count(), "the two-variant product should expose SKU editors").toBeGreaterThan(0);
    const inlineValues = await inlineSkus.evaluateAll((inputs) => inputs.map((input) => input.value));
    expect(inlineValues).toContain("MUG-300-آجری");
    const inlineMetrics = await inlineSkus.evaluateAll((inputs) => inputs.map((input) => ({
      value: input.value,
      dir: input.getAttribute("dir"),
      direction: getComputedStyle(input).direction,
      clientWidth: input.clientWidth,
      scrollWidth: input.scrollWidth,
    })));
    const mixedSku = inlineMetrics.find((input) => input.value === "MUG-300-آجری");
    expect(mixedSku).toBeTruthy();
    expect(mixedSku.dir).toBe("ltr");
    expect(mixedSku.direction).toBe("ltr");
    expect(mixedSku.clientWidth).toBeGreaterThanOrEqual(120);
    expect(mixedSku.scrollWidth, "mixed Persian-Latin SKU must fit without clipping").toBeLessThanOrEqual(mixedSku.clientWidth);
    for (const input of await inlineSkus.all()) {
      await expect(input).toHaveAttribute("dir", "ltr");
      expect(await input.evaluate((element) => getComputedStyle(element).direction)).toBe("ltr");
    }

    const variantUrl = await firstProductVariantUrl(page);
    await page.goto(new URL(variantUrl, BASE_URL).href, { waitUntil: "networkidle" });
    const standaloneSku = page.locator("#id_sku");
    await expect(standaloneSku).toHaveAttribute("dir", "ltr");
    expect(await standaloneSku.evaluate((input) => getComputedStyle(input).direction)).toBe("ltr");
  });
});

test.describe("fieldset help text stays inside at every width", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only; this spec sets its own viewport");
    await login(page);
  });

  for (const width of [320, 375, 768, 1024, 1280, 1440, 1920]) {
    test.describe(`${width}px help`, () => {
      test.use({ viewport: { width, height: 1000 } });

      test("product and order help blocks stay within their nearest fieldsets", async ({ page }) => {
        for (const form of [
          { label: "two-variant product", getUrl: firstProductWithVariantsUrl },
          { label: "order", getUrl: firstOrderUrl },
        ]) {
          const url = await form.getUrl(page);
          await page.goto(new URL(url, BASE_URL).href, { waitUntil: "networkidle" });
          await assertNoHorizontalOverflow(page);
          await assertHelpTextInsideFieldset(page);
        }
      });
    });
  }
});

test.describe("nine-digit numeric changelist inputs", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only");
    await login(page);
  });

  for (const width of [1280, 1440, 1920]) {
    test.describe(`${width}px product changelist`, () => {
      test.use({ viewport: { width, height: 900 } });

      test("price, compare-at and stock inputs show 123456789 without clipping, and headers wrap only at words", async ({ page }) => {
        await page.goto(`${BASE_URL}/admin/products/product/`, { waitUntil: "networkidle" });
        await assertProductHeaderWrapping(page);
        await assertNineDigitNumericInputs(
          page,
          "/admin/products/product/",
          "#result_list tbody td.field-price input[type=number], " +
            "#result_list tbody td.field-compare_at_price input[type=number], " +
            "#result_list tbody td.field-stock_quantity input[type=number]"
        );
      });
    });
  }

  test.describe("other editable admin lists at 1280px", () => {
    test.use({ viewport: { width: 1280, height: 900 } });

    test("brand display-order values remain readable", async ({ page }) => {
      await assertNineDigitNumericInputs(
        page,
        "/admin/products/brand/",
        "#result_list tbody td.field-display_order input[type=number]"
      );
    });

    test("banner ordering values remain readable", async ({ page }) => {
      await assertNineDigitNumericInputs(
        page,
        "/admin/banners/banner/",
        "#result_list tbody td.field-ordering input[type=number]"
      );
    });
  });
});

test.describe("product changelist SKUs remain fully visible on desktop", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only");
    await login(page);
  });

  for (const width of [1024, 1280, 1440]) {
    test.describe(`${width}px product changelist`, () => {
      test.use({ viewport: { width, height: 900 } });

      test("every product SKU is fully visible without ellipsis", async ({ page }) => {
        await page.goto(`${BASE_URL}/admin/products/product/`, { waitUntil: "networkidle" });
        const skus = await page.locator(
          "#result_list tbody .cusin-product-summary__sku"
        ).evaluateAll((elements) => elements.map((element) => {
          const style = getComputedStyle(element);
          return {
            text: element.textContent.trim(),
            title: element.getAttribute("title"),
            clientWidth: element.clientWidth,
            scrollWidth: element.scrollWidth,
            direction: style.direction,
            whiteSpace: style.whiteSpace,
            textOverflow: style.textOverflow,
            fontFamily: style.fontFamily,
          };
        }));

        expect(skus.length, "product changelist should include SKU tokens").toBeGreaterThan(0);
        for (const sku of skus) {
          expect(sku.text, `SKU should match its complete title: ${JSON.stringify(sku)}`).toBe(sku.title);
          expect(sku.text).not.toContain("…");
          expect(sku.text).not.toContain("...");
          expect(sku.direction).toBe("ltr");
          expect(sku.whiteSpace).toBe("nowrap");
          expect(sku.textOverflow).not.toBe("ellipsis");
          expect(sku.fontFamily).toContain("monospace");
          expect(sku.clientWidth, `SKU should have measurable width: ${JSON.stringify(sku)}`).toBeGreaterThan(0);
          expect(sku.scrollWidth, `SKU should not be clipped: ${JSON.stringify(sku)}`).toBeLessThanOrEqual(sku.clientWidth);
        }
      });
    });
  }
});

test.describe("product changelist stock badges show exceptions only", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only");
    await login(page);
  });

  test("sufficient stock is not repeated as a badge beside its input", async ({ page }) => {
    await page.goto(`${BASE_URL}/admin/products/product/?q=MUG-300`, { waitUntil: "networkidle" });
    const row = page.locator("#result_list tbody tr").filter({
      has: page.locator('.cusin-product-summary__sku[title="MUG-300"]'),
    });
    await expect(row).toHaveCount(1);
    const stockInput = row.locator("td.field-stock_quantity input");
    await expect(stockInput).toHaveValue("40");
    expect(Number(await stockInput.inputValue()), "MUG-300 is a sufficiently stocked demo product").toBeGreaterThan(5);
    await expect(row.locator("td.field-stock_quantity .cusin-badge")).toHaveCount(0);
  });
});

test.describe("product changelist row elements never overlap", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only");
    await login(page);
  });

  for (const width of [320, 375, 768, 1024, 1280, 1440, 1920]) {
    test.describe(`${width}px rows`, () => {
      test.use({ viewport: { width, height: 1000 } });

      test("stock badges, edit inputs and all visible row items remain separate", async ({ page }) => {
        await assertProductRowItemsDoNotOverlap(page);
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
          await expect(filterPanel).toHaveClass(/is-side-sheet/);
          await expect(filterPanel).toHaveAttribute("aria-labelledby", await filterTrigger.getAttribute("id"));
          const sheet = await filterPanel.boundingBox();
          expect(sheet.x).toBeGreaterThanOrEqual(0);
          expect(sheet.x + sheet.width).toBeLessThanOrEqual(viewport.width + 0.5);
          expect(sheet.y).toBeLessThanOrEqual(8.5);
          expect(sheet.y + sheet.height).toBeGreaterThanOrEqual(viewport.height - 8.5);
        } else {
          await expect(filterPanel).not.toHaveClass(/is-sheet/);
          const panelWidth = await filterPanel.evaluate((el) => el.getBoundingClientRect().width);
          expect(panelWidth, "desktop filters should remain a bounded popover").toBeLessThanOrEqual(500);
          if (viewport.width >= 1280) {
            const anchor = await page.evaluate(() => {
              const trigger = document.querySelector(".cusin-filter-menu [data-cusin-menu-trigger]").getBoundingClientRect();
              const panel = document.querySelector("#cusin-menu-panel-filters").getBoundingClientRect();
              const rtl = getComputedStyle(document.documentElement).direction === "rtl";
              return { trigger: rtl ? trigger.right : trigger.left, panel: rtl ? panel.right : panel.left };
            });
            expect(Math.abs(anchor.panel - anchor.trigger), "desktop filter panel should anchor to its trigger edge").toBeLessThanOrEqual(1);
          }
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

test.describe("changelist filter cleanup and active chips", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");
  test.use({ viewport: { width: 1280, height: 900 } });

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only");
    await login(page);
  });

  test("remove count links and arrow labels; expose removable chips above filtered results", async ({ page }) => {
    const filteredUrl = `${BASE_URL}/admin/products/product/?is_active__exact=1&q=MUG-300`;
    await page.goto(filteredUrl, { waitUntil: "networkidle" });
    await expect(page.locator("#changelist-filter-extra-actions")).toHaveCount(0);
    const groups = page.locator("#cusin-menu-panel-filters #changelist-filter details");
    expect(await groups.evaluateAll((items) => items.map((item) => item.open))).toEqual(
      Array(await groups.count()).fill(false),
    );
    const summaryStyle = await groups.first().locator(":scope > summary").evaluate((el) => ({
      minHeight: getComputedStyle(el).minHeight,
      padding: getComputedStyle(el).padding,
    }));
    expect(summaryStyle).toEqual({ minHeight: "34px", padding: "4px 6px" });

    const chips = page.locator(".cusin-active-filters");
    await expect(chips).toBeVisible();
    const individual = chips.locator(".cusin-filter-chip:not(.cusin-filter-chip--clear)").first();
    await expect(individual).toHaveText("بله");
    const clearAll = chips.locator(".cusin-filter-chip--clear");
    await expect(clearAll).toHaveText("حذف همهٔ فیلترها");
    const clearUrl = new URL(await clearAll.getAttribute("href"), BASE_URL);
    expect(clearUrl.searchParams.get("q")).toBe("MUG-300");
    expect(clearUrl.searchParams.has("is_active__exact")).toBe(false);
    const aboveResults = await chips.evaluate((el) => Boolean(
      el.compareDocumentPosition(document.querySelector("#result_list")) & Node.DOCUMENT_POSITION_FOLLOWING
    ));
    expect(aboveResults).toBe(true);

    await individual.click();
    await page.waitForURL((url) => !url.searchParams.has("is_active__exact"));
    await expect(page.locator(".cusin-active-filters")).toHaveCount(0);

    await page.goto(filteredUrl, { waitUntil: "networkidle" });
    await page.locator(".cusin-filter-chip--clear").click();
    await page.waitForURL((url) => url.searchParams.get("q") === "MUG-300" && !url.searchParams.has("is_active__exact"));
    await expect(page.locator(".cusin-active-filters")).toHaveCount(0);

    await page.goto(`${BASE_URL}/admin/orders/order/`, { waitUntil: "networkidle" });
    await expect(page.locator("#changelist-filter-extra-actions")).toHaveCount(0);
    const dateTrigger = page.locator(".cusin-date-menu [data-cusin-menu-trigger]");
    if (await dateTrigger.count()) {
      await dateTrigger.click();
      const dateLabels = await page.locator("#cusin-menu-panel-date-range:not([hidden]) .cusin-menu-item").allTextContents();
      expect(dateLabels.length).toBeGreaterThan(0);
      expect(dateLabels.some((label) => /^[‹›←→]/.test(label.trim()))).toBe(false);
    }
  });
});

test.describe("desktop order-status column layout", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");
  test.use({ viewport: { width: 1280, height: 900 } });

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only");
    await login(page);
  });

  test("status badges remain inside their own cells without overlapping", async ({ page }) => {
    await page.goto(`${BASE_URL}/admin/orders/order/`, { waitUntil: "networkidle" });
    const badges = await page.locator(
      "#result_list tbody td.field-status_badge .cusin-badge, #result_list tbody td.field-payment_badge .cusin-badge",
    ).evaluateAll((items) => items.map((badge) => {
      const cell = badge.parentElement;
      const cellBox = cell.getBoundingClientRect();
      const badgeBox = badge.getBoundingClientRect();
      const style = getComputedStyle(cell);
      const innerLeft = cellBox.left + parseFloat(style.paddingLeft);
      const innerRight = cellBox.right - parseFloat(style.paddingRight);
      return {
        text: badge.textContent.trim(),
        badgeLeft: badgeBox.left,
        badgeRight: badgeBox.right,
        innerLeft,
        innerRight,
        scrollWidth: badge.scrollWidth,
        clientWidth: badge.clientWidth,
      };
    }));

    expect(badges.length, "the order list should have visible status examples").toBeGreaterThan(0);
    for (const badge of badges) {
      expect(badge.badgeLeft, `${badge.text} should stay within its column's left edge`).toBeGreaterThanOrEqual(badge.innerLeft - 0.5);
      expect(badge.badgeRight, `${badge.text} should stay within its column's right edge`).toBeLessThanOrEqual(badge.innerRight + 0.5);
      expect(badge.scrollWidth, `${badge.text} should wrap rather than clip`).toBeLessThanOrEqual(badge.clientWidth + 1);
    }
  });
});

test.describe("product and image import pages at 320px", () => {
  test.skip(!USER || !PASSWORD, "set E2E_ADMIN_USER and E2E_ADMIN_PASSWORD to run");
  test.use({ viewport: { width: 320, height: 760 } });

  test("keep all copy readable and prevent page-level horizontal overflow", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "desktop project only; this test sets its own viewport");
    await login(page);

    for (const pagePath of [
      "/admin/products/product/import/",
      "/admin/products/product/image-import/",
    ]) {
      await page.goto(`${BASE_URL}${pagePath}`, { waitUntil: "networkidle" });
      await expect(page.locator("body")).toHaveClass(/cusin-import-page/);
      await assertNoHorizontalOverflow(page);
      await assertAdminTypography(page);
      const upload = page.locator('#content input[type="file"]');
      await expect(upload).toBeVisible();
      const bounds = await upload.boundingBox();
      expect(bounds.x, `${pagePath} file control should stay inside the viewport`).toBeGreaterThanOrEqual(0);
      expect(bounds.x + bounds.width, `${pagePath} file control should stay inside the viewport`).toBeLessThanOrEqual(320);
    }
  });
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
        const productUrl = await firstProductWithVariantsUrl(page);
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
