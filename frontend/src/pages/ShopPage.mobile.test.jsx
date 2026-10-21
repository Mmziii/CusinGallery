/**
 * Audit 19 item 1: the phone shop toolbar.
 *
 * The long filter column that used to sit above the products is gone on a
 * phone: a sticky bar under the header carries «فیلترها» (with the count of
 * active filters), «مرتب‌سازی» and the result count. Both controls open a
 * bottom sheet -- filters get an «اعمال» button -- and paging is a single
 * «نمایش کالاهای بیشتر» button that walks the same ?page= URLs.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import ShopPage from "./ShopPage";

const originalAdapter = apiClient.defaults.adapter;
const originalMatchMedia = window.matchMedia;

const makeProduct = (id, name) => ({
  id,
  name,
  slug: `product-${id}`,
  stock_status: "in_stock",
  is_new: false,
  brand: null,
  primary_image: null,
  images: [],
  price_info: { price: 100000 + id, compare_at_price: null, discount_percentage: 0 },
});

let productRequests = [];

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (/\/products\/facets\//.test(url)) {
      return { data: { count: 0, next: null, previous: null, results: [] }, status: 200, statusText: "OK", headers: {}, config };
    }
    if (/^\/categories\//.test(url) || /^\/brands\//.test(url)) {
      return { data: { count: 0, next: null, previous: null, results: [] }, status: 200, statusText: "OK", headers: {}, config };
    }
    if (/\/products\//.test(url)) {
      productRequests.push(config.params || {});
      const page = Number(config.params?.page || 1);
      const start = (page - 1) * 20;
      return {
        data: {
          count: 40,
          next: null,
          previous: null,
          results: Array.from({ length: 20 }, (_, index) =>
            makeProduct(start + index + 1, `کالای صفحه ${page} شماره ${index + 1}`)
          ),
        },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      };
    }
    return originalAdapter(config);
  };
});

afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});

function setViewport(mobile) {
  window.matchMedia = (query) => ({
    matches: mobile && query.includes("max-width: 767px"),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

function renderShop(query = "") {
  return render(
    <MemoryRouter initialEntries={[`/shop/${query}`]}>
      <ShopPage />
    </MemoryRouter>
  );
}

afterEach(() => {
  cleanup();
  productRequests = [];
  window.matchMedia = originalMatchMedia;
});

describe("phone shop toolbar", () => {
  it("replaces the sidebar with the sticky bar and the result count", async () => {
    setViewport(true);
    renderShop();
    await screen.findByText("کالای صفحه ۱ شماره ۱");

    // The long filter block is not rendered on a phone at all.
    expect(document.querySelector(".shop__sidebar")).toBeNull();
    const bar = document.querySelector(".shop__mobile-bar");
    expect(bar).toBeTruthy();
    // Sticky travel box = the results column: the bar must NOT be a direct
    // child of the `.shop` grid (a grid item only sticks within its own row).
    expect(bar.parentElement.classList.contains("shop__main")).toBe(true);
    expect(bar.closest(".shop").firstElementChild).not.toBe(bar);
    // Result count, Persian digits.
    expect(bar.querySelector(".shop__mobile-count").textContent).toBe("۴۰ کالا");
    expect(screen.getByRole("button", { name: /^فیلترها/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^مرتب‌سازی$/ })).toBeTruthy();
  });

  it("adds a visually hidden products heading before the product grid", async () => {
    setViewport(true);
    const { container } = renderShop();
    await screen.findByText("کالای صفحه ۱ شماره ۱");

    const pageTitle = container.querySelector(".shop__heading h1");
    const productsHeading = screen.getByRole("heading", { level: 2, name: "محصولات" });
    const grid = container.querySelector(".shop__results .product-grid");
    expect(productsHeading.className).toContain("sr-only");
    expect(pageTitle.compareDocumentPosition(productsHeading) & 4).toBeTruthy();
    expect(productsHeading.compareDocumentPosition(grid) & 4).toBeTruthy();
  });

  it("opens the filters as a bottom sheet with «اعمال» and the active-filter count", async () => {
    setViewport(true);
    renderShop("?brand=unique&in_stock=true");
    await screen.findByText("کالای صفحه ۱ شماره ۱");

    const button = screen.getByRole("button", { name: /^فیلترها/ });
    expect(button.textContent).toContain("۲"); // two active filters
    fireEvent.click(button);

    const sheet = document.getElementById("shop-filters-sheet");
    expect(sheet).toBeTruthy();
    expect(sheet.getAttribute("aria-modal")).toBe("true");
    expect(sheet.querySelector(".sheet__head h2").textContent).toContain("۲");
    // The real filter controls live in the sheet, plus the «اعمال» button.
    expect(sheet.querySelector('input[aria-label="جستجوی برند"]')).toBeTruthy();
    const apply = screen.getByRole("button", { name: "اعمال" });
    fireEvent.click(apply);
    await waitFor(() => expect(document.getElementById("shop-filters-sheet")).toBeNull());
  });

  it("opens the sorting as a bottom sheet with radio options that re-order the list", async () => {
    setViewport(true);
    renderShop();
    await screen.findByText("کالای صفحه ۱ شماره ۱");

    fireEvent.click(screen.getByRole("button", { name: /^مرتب‌سازی$/ }));
    const sheet = document.getElementById("shop-sort-sheet");
    expect(sheet).toBeTruthy();
    const radios = sheet.querySelectorAll('input[type="radio"]');
    expect(radios.length).toBe(4);
    expect(sheet.querySelector('input[value="newest"]').checked).toBe(true);

    fireEvent.click(sheet.querySelector('input[value="price_asc"]'));
    await waitFor(() => expect(productRequests.some((p) => p.ordering === "price_asc")).toBe(true));
    await waitFor(() => expect(document.getElementById("shop-sort-sheet")).toBeNull());
  });

  it("loads more with the same ?page= URL and appends the next page", async () => {
    setViewport(true);
    renderShop();
    await screen.findByText("کالای صفحه ۱ شماره ۱");

    // Page-number links are replaced by one button on a phone.
    expect(document.querySelector(".pagination")).toBeNull();
    const more = screen.getByRole("button", { name: "نمایش کالاهای بیشتر" });
    fireEvent.click(more);

    await screen.findByText("کالای صفحه ۲ شماره ۱");
    // Page 1 is still rendered -- appended, not replaced.
    expect(screen.getByText("کالای صفحه ۱ شماره ۱")).toBeTruthy();
    expect(productRequests.some((p) => String(p.page) === "2")).toBe(true);
  });

  it("keeps the desktop sidebar and numbered pagination at ≥768px", async () => {
    setViewport(false);
    renderShop();
    await screen.findByText("کالای صفحه ۱ شماره ۱");

    expect(document.querySelector(".shop__mobile-bar")).toBeNull();
    expect(document.querySelector(".shop__sidebar")).toBeTruthy();
    expect(document.getElementById("shop-filters")).toBeTruthy();
    expect(document.querySelector(".pagination")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "نمایش کالاهای بیشتر" })).toBeNull();
  });
});
