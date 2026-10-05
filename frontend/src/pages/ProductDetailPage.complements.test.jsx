/**
 * Part R5 item 9: the «پیشنهاد همراه» (complements) section on the
 * product page. The API only ever returns active + in-stock candidates,
 * so these tests verify rendering, selection state, and the bulk
 * "add selected to cart" action against the guest cart (no server).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

describe("product page complements section", () => {
  it("renders the section with every candidate preselected", async () => {
    renderPage();
    expect(await screen.findByText("پیشنهاد همراه")).toBeTruthy();
    expect(await screen.findByText("کفچک استیل")).toBeTruthy();
    expect(await screen.findByText("آبکش بلور")).toBeTruthy();

    const boxes = document.querySelectorAll(".complements__card input[type=checkbox]");
    expect(boxes.length).toBe(2);
    boxes.forEach((box) => expect(box.checked).toBe(true));
  });

  it("adds only the selected complements to the guest cart", async () => {
    renderPage();
    await screen.findByText("پیشنهاد همراه");

    // Uncheck the second complement, keep the first.
    const boxes = document.querySelectorAll(".complements__card input[type=checkbox]");
    fireEvent.click(boxes[1]);
    expect(boxes[1].checked).toBe(false);

    fireEvent.click(screen.getByText("افزودن انتخاب‌شده‌ها به سبد"));

    await waitFor(() => {
      const lines = useCartStore.getState().guestLines;
      expect(lines.length).toBe(1);
      expect(lines[0]).toMatchObject({ product_id: 11, quantity: 1 });
    });
    expect(await screen.findByText("کالاهای انتخاب‌شده به سبد خرید اضافه شدند.")).toBeTruthy();
  });

  it("adds all selected complements when none are unchecked", async () => {
    renderPage();
    await screen.findByText("پیشنهاد همراه");
    fireEvent.click(screen.getByText("افزودن انتخاب‌شده‌ها به سبد"));

    await waitFor(() => {
      const lines = useCartStore.getState().guestLines;
      expect(lines.map((l) => l.product_id).sort()).toEqual([11, 12]);
    });
  });

  it("disables the button when nothing is selected", async () => {
    renderPage();
    await screen.findByText("پیشنهاد همراه");
    const boxes = document.querySelectorAll(".complements__card input[type=checkbox]");
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);

    const button = screen.getByText("افزودن انتخاب‌شده‌ها به سبد");
    expect(button.disabled).toBe(true);
  });

  it("renders nothing when the product has no complements", async () => {
    renderPage("/products/no-complements/");
    await screen.findByRole("heading", { level: 1, name: "قابلمه گرانیتی" });
    expect(screen.queryByText("پیشنهاد همراه")).toBeNull();
  });

  it("records the view in browser-local storage (item 10)", async () => {
    renderPage();
    await screen.findByText("پیشنهاد همراه");
    await waitFor(() => {
      expect(JSON.parse(localStorage.getItem("cusin_recently_viewed"))).toEqual([1]);
    });
  });
});
