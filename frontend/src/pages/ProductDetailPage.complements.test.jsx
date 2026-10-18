import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import useCartStore from "../store/useCartStore";
import ProductDetailPage from "./ProductDetailPage";

const priceInfo = (price) => ({
  price,
  compare_at_price: null,
  discount_percentage: 0,
  is_on_sale: false,
  discount_amount: 0,
});

const PRODUCT = {
  id: 1,
  name: "قابلمه گرانیتی",
  slug: "base-pot",
  sku: "POT-1",
  short_description: "قابلمه",
  description: "توضیحات کامل",
  category: { id: 1, name: "قابلمه", slug: "pots" },
  brand: null,
  price_info: priceInfo(850000),
  primary_image: null,
  stock_status: "in_stock",
  is_in_stock: true,
  is_featured: false,
  is_new: false,
  is_best_seller: false,
  images: [],
  variants: [],
  specifications: [],
  related_products: [],
  complements: [
    { id: 11, name: "کفچک استیل", slug: "spoon", price_info: priceInfo(120000), primary_image: null, stock_status: "in_stock", is_in_stock: true },
    { id: 12, name: "آبکش بلور", slug: "strainer", price_info: priceInfo(90000), primary_image: null, stock_status: "in_stock", is_in_stock: true },
  ],
};

const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (url === "/products/base-pot/") {
      return { data: PRODUCT, status: 200, statusText: "OK", headers: {}, config };
    }
    if (url.startsWith("/products/no-complements/")) {
      return { data: { ...PRODUCT, slug: "no-complements", complements: [] }, status: 200, statusText: "OK", headers: {}, config };
    }
    if (/^\/reviews\/product\/\d+\/summary\/$/.test(url)) {
      return { data: { count: 0, average_rating: null }, status: 200, statusText: "OK", headers: {}, config };
    }
    if (/^\/reviews\/product\/\d+\/$/.test(url)) {
      return { data: { count: 0, next: null, previous: null, results: [] }, status: 200, statusText: "OK", headers: {}, config };
    }
    return originalAdapter(config);
  };
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
beforeEach(() => {
  localStorage.clear();
  useCartStore.setState({ guestLines: [], guestProducts: {}, cart: null, error: null });
});
afterEach(() => {
  cleanup();
});

function renderPage(path = "/products/base-pot/") {
  // useParams() only resolves inside a matching <Route>, so mount the
  // page through a route table exactly like the real app does.
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/products/:slug" element={<ProductDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("product page below-the-product content", () => {
  it("does not render complements or their bulk-purchase action even when the API includes them", async () => {
    const { container } = renderPage();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });
    expect(screen.queryByText("پیشنهاد همراه")).toBeNull();
    expect(screen.queryByText("کفچک استیل")).toBeNull();
    expect(screen.queryByText("افزودن انتخاب‌شده‌ها به سبد")).toBeNull();
    expect(container.querySelector(".complements")).toBeNull();
    expect(screen.getByRole("heading", { name: "نظرات کاربران" })).toBeTruthy();
  });

  it("records the view in browser-local storage", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });
    await waitFor(() => {
      expect(JSON.parse(localStorage.getItem("cusin_recently_viewed"))).toEqual([1]);
    });
  });
});
