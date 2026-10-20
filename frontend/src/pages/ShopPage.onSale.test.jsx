/**
 * «مشاهده همه» → «فقط کالاهای تخفیف‌دار».
 *
 * The daily-deals band links to /shop/?on_sale=true; the backend filter
 * accepts 1/true/yes (apps/products/filters.py). The checkbox must read the
 * same values -- an old `?on_sale=1` bookmark used to land on the shop with
 * the filter visibly OFF while the results were filtered.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import ShopPage from "./ShopPage";
import { isTruthyParam } from "../utils/queryFlags";

const originalAdapter = apiClient.defaults.adapter;
let productRequests = [];

const EMPTY = { count: 0, next: null, previous: null, results: [] };

beforeEach(() => {
  productRequests = [];
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (url.includes("/products/facets/")) {
      return { data: EMPTY, status: 200, statusText: "OK", headers: {}, config };
    }
    if (url.startsWith("/categories/") || url.startsWith("/brands/")) {
      return { data: EMPTY, status: 200, statusText: "OK", headers: {}, config };
    }
    if (url.startsWith("/products/")) {
      productRequests.push(config.params || {});
      return { data: EMPTY, status: 200, statusText: "OK", headers: {}, config };
    }
    return originalAdapter(config);
  };
});

afterEach(() => {
  cleanup();
  apiClient.defaults.adapter = originalAdapter;
});

function renderShop(query = "") {
  return render(
    <MemoryRouter initialEntries={[`/shop/${query}`]}>
      <ShopPage />
    </MemoryRouter>
  );
}

const onSaleBox = () => screen.getByRole("checkbox", { name: "فقط کالاهای تخفیف‌دار" });

describe("shop on_sale query flag", () => {
  it.each(["true", "1", "yes", "TRUE"])("checks the box for on_sale=%s and forwards it", async (value) => {
    renderShop(`?on_sale=${value}`);
    await waitFor(() => expect(onSaleBox().checked).toBe(true));
    await waitFor(() => expect(productRequests.at(-1)).toMatchObject({ on_sale: value }));
  });

  it.each(["", "false", "0", "no"])("leaves the box unchecked for on_sale=%s", async (value) => {
    renderShop(value ? `?on_sale=${value}` : "");
    await waitFor(() => expect(productRequests.length).toBeGreaterThan(0));
    expect(onSaleBox().checked).toBe(false);
  });

  it("ignores an absent flag", async () => {
    renderShop();
    await waitFor(() => expect(productRequests.length).toBeGreaterThan(0));
    expect(onSaleBox().checked).toBe(false);
  });
});

describe("isTruthyParam", () => {
  it.each(["1", "true", "TRUE", " yes ", "on"])("reads %s as true", (value) => {
    expect(isTruthyParam(value)).toBe(true);
  });

  it.each([null, undefined, "", "0", "false", "no", "off", "whatever"])("reads %s as false", (value) => {
    expect(isTruthyParam(value)).toBe(false);
  });
});
