/**
 * Part S5 item 5: what the product page is allowed to say.
 *
 * The reported problem: the product page carried a shipping/return/
 * packaging block ("ارسال: عادی ۳ تا ۵ روز …", "بسته‌بندی: …",
 * "مرجوعی: …"), so delivery promises sat on every product while the real
 * costs and methods are calculated in the cart/checkout. These tests pin
 * the content rules: NO shipping text on the product page, and everything
 * a shopper needs to buy is still there.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import Footer from "../components/Footer";
import apiClient from "../services/apiClient";
import ProductDetailPage from "./ProductDetailPage";

// Phrases that must never appear on a product page again.
const SHIPPING_PHRASES = [
  "ارسال:",
  "بسته‌بندی:",
  "مرجوعی:",
  "۳ تا ۵ روز",
  "اکسپرس",
  "ضدضربه",
  "هزینهٔ ارسال",
  "هزینه ارسال",
];

const priceInfo = (price) => ({
  price,
  compare_at_price: 990000,
  discount_percentage: 10,
  is_on_sale: true,
  discount_amount: 99000,
});

const PRODUCT = {
  id: 7,
  name: "قابلمه گرانیتی",
  slug: "pan",
  sku: "PAN-1",
  short_description: "قابلمه گرانیتی با کف ضخیم",
  description: "توضیحات کامل محصول",
  category: { id: 1, name: "قابلمه", slug: "pots" },
  brand: { id: 2, name: "یونیک", slug: "unique" },
  price_info: priceInfo(891000),
  stock_status: "in_stock",
  is_in_stock: true,
  is_featured: false,
  is_new: false,
  is_best_seller: false,
  images: [
    { id: 1, image: "/media/products/pan.jpg", alt_text: "قابلمه", is_primary: true, ordering: 0 },
  ],
  primary_image: { id: 1, image: "/media/products/pan.jpg" },
  variants: [],
  specifications: [
    { attribute: "جنس", values: ["گرانیت", "آلومینیوم"] },
    { attribute: "قطر", values: ["۲۴ سانتی‌متر"] },
  ],
  related_products: [
    {
      id: 8,
      name: "قابلمه کوچک",
      slug: "small-pan",
      price_info: priceInfo(500000),
      stock_status: "in_stock",
      is_in_stock: true,
      primary_image: { id: 2, image: "/media/products/small.jpg" },
    },
  ],
  complements: [
    {
      id: 9,
      name: "درب شیشه‌ای",
      slug: "glass-lid",
      price: 250000,
      price_info: priceInfo(250000),
      stock_status: "in_stock",
      is_in_stock: true,
      primary_image: { id: 3, image: "/media/products/lid.jpg" },
    },
  ],
};

const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (url === "/products/pan/") {
      return { data: PRODUCT, status: 200, statusText: "OK", headers: {}, config };
    }
    if (/^\/reviews\//.test(url)) {
      return { data: { count: 0, results: [] }, status: 200, statusText: "OK", headers: {}, config };
    }
    return originalAdapter(config);
  };
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
afterEach(cleanup);

function renderProduct() {
  return render(
    <MemoryRouter initialEntries={["/products/pan/"]}>
      <Routes>
        <Route path="/products/:slug/" element={<ProductDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("Product page content (Part S5 item 5)", () => {
  it("shows no shipping, delivery-cost, return or packaging content", async () => {
    const { container } = renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });

    const text = container.textContent;
    for (const phrase of SHIPPING_PHRASES) {
      expect(text).not.toContain(phrase);
    }
    // The old assurances block (and its class) is gone for good.
    expect(container.querySelector(".product-detail__assurances")).toBeNull();
  });

  it("keeps everything a shopper needs to buy", async () => {
    const { container } = renderProduct();
    const heading = await screen.findByRole("heading", { name: "قابلمه گرانیتی" });

    // Title, brand, short description and price.
    expect(heading.tagName).toBe("H1");
    expect(container.textContent).toContain("برند: یونیک");
    expect(container.textContent).toContain("قابلمه گرانیتی با کف ضخیم");
    expect(container.querySelector(".price__current")).not.toBeNull();

    // Stock state, quantity picker and the add-to-cart button.
    expect(container.querySelector(".stock")).not.toBeNull();
    expect(screen.getByRole("button", { name: "کاهش" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "افزایش" })).toBeTruthy();
    // The main buy button and the mobile sticky bar both offer it.
    expect(screen.getAllByRole("button", { name: "افزودن به سبد خرید" }).length).toBeGreaterThan(0);
  });

  it("keeps the description, the attributes table, complements and related products", async () => {
    const { container } = renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });

    expect(screen.getByRole("heading", { name: "توضیحات" })).toBeTruthy();
    expect(container.textContent).toContain("توضیحات کامل محصول");

    const specs = container.querySelector("table.specs");
    expect(specs).not.toBeNull();
    expect(within(specs).getByText("جنس")).toBeTruthy();
    expect(within(specs).getByText("گرانیت، آلومینیوم")).toBeTruthy();

    expect(screen.getByRole("heading", { name: "پیشنهاد همراه" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "محصولات مرتبط" })).toBeTruthy();
  });

  it("keeps the SKU in the machine-readable product data (it was never a visible line)", async () => {
    renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });

    const jsonLd = JSON.parse(
      document.head.querySelector('script[id="product-jsonld"]')?.textContent || "{}"
    );
    expect(jsonLd.sku).toBe("PAN-1");
  });

  it("still links the shipping policy page from the footer (where it belongs)", () => {
    render(
      <MemoryRouter>
        <Footer />
      </MemoryRouter>
    );
    const link = screen.getByRole("link", { name: "ارسال و مرجوعی" });
    expect(link.getAttribute("href")).toBe("/shipping-returns/");
  });
});
