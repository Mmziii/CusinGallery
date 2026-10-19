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
import fs from "node:fs";
import path from "node:path";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
const originalMatchMedia = window.matchMedia;
let productResponse = PRODUCT;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (/^\/products\/[^/]+\/$/.test(url)) {
      return { data: productResponse, status: 200, statusText: "OK", headers: {}, config };
    }
    if (url === "/products/" && config.params?.ids === "99") {
      return { data: { count: 1, next: null, results: [{ ...PRODUCT, id: 99, slug: "recent", name: "محصول دیده‌شده" }] }, status: 200, statusText: "OK", headers: {}, config };
    }
    if (/^\/reviews\//.test(url)) {
      return { data: { count: 0, next: null, previous: null, results: [] }, status: 200, statusText: "OK", headers: {}, config };
    }
    return originalAdapter(config);
  };
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
afterEach(() => {
  cleanup();
  productResponse = PRODUCT;
  window.matchMedia = originalMatchMedia;
  localStorage.clear();
});

function renderProduct(path = "/products/pan/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/products/:slug/" element={<ProductDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("Product page content (Part S5 item 5)", () => {
  it("links the flagged fallback root to the shop, not a hardcoded kitchen filter", async () => {
    productResponse = { ...PRODUCT, category: { ...PRODUCT.category, is_catalog_root: false, ancestors: [{ name: "آشپزخانه", slug: "kitchen-root-2", is_catalog_root: true }] } };
    renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });
    expect(screen.getByRole("link", { name: "آشپزخانه" }).getAttribute("href")).toBe("/shop/");
    expect(screen.getByRole("link", { name: "قابلمه", exact: true }).getAttribute("href")).toBe("/shop/?category=pots");
    // The JSON-LD block is appended in a passive effect; findByRole can
    // resolve on the same commit, so wait for the script itself.
    const breadcrumbScript = await waitFor(() => {
      const node = document.getElementById("breadcrumb-jsonld");
      expect(node).toBeTruthy();
      return node;
    });
    const crumbs = JSON.parse(breadcrumbScript.textContent);
    expect(crumbs.itemListElement[1].item).toMatch(/\/shop\/$/);
  });

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
    expect(screen.getByRole("link", { name: "برند: یونیک" }).getAttribute("href")).toBe("/brands/unique/");
    expect(container.textContent).toContain("قابلمه گرانیتی با کف ضخیم");
    expect(container.querySelector(".price__current")).not.toBeNull();

    // Stock state, quantity picker and the add-to-cart button.
    expect(container.querySelector(".stock")).not.toBeNull();
    expect(screen.getByRole("button", { name: "کاهش" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "افزایش" })).toBeTruthy();
    // The main buy button and the mobile sticky bar both offer it.
    expect(screen.getAllByRole("button", { name: "افزودن به سبد خرید" }).length).toBeGreaterThan(0);
  });

  it("keeps the full description and specifications in the info column beside the gallery", async () => {
    const { container } = renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });

    expect(screen.getByRole("heading", { name: "توضیحات" })).toBeTruthy();
    expect(container.textContent).toContain("توضیحات کامل محصول");

    const specs = container.querySelector("table.specs");
    expect(specs).not.toBeNull();
    expect(within(specs).getByText("جنس")).toBeTruthy();
    expect(within(specs).getByText("گرانیت، آلومینیوم")).toBeTruthy();

    const info = container.querySelector(".product-detail__info");
    const body = container.querySelector(".product-detail__body");
    expect(info.contains(specs)).toBe(true);
    expect(info.contains(container.querySelector(".product-detail__description"))).toBe(true);
    expect(body.children[0].className).toBe("product-detail__gallery");
    expect(body.children[1]).toBe(info);
    expect(container.querySelector(".product-detail__extra")).toBeNull();
    expect(screen.queryByRole("heading", { name: "پیشنهاد همراه" })).toBeNull();
    expect(screen.getByRole("heading", { name: "محصولات مرتبط" })).toBeTruthy();
  });

  it("has ONLY related products, reviews and recently viewed below the primary row, in that order", async () => {
    localStorage.setItem("cusin_recently_viewed", JSON.stringify([99]));
    const { container } = renderProduct();
    await screen.findByText("اخیراً دیده‌اید");
    const sections = container.querySelectorAll(".product-detail > section");
    expect([...sections].map((section) => section.querySelector("h2")?.textContent)).toEqual([
      "محصولات مرتبط", "نظرات کاربران", "اخیراً دیده‌اید",
    ]);
    const body = container.querySelector(".product-detail__body");
    expect(body.contains(sections[0])).toBe(false);
  });

  it("renders Persian digits in product names/descriptions without changing the slug or SKU", async () => {
    productResponse = {
      ...PRODUCT,
      name: "قابلمه مدل 123",
      slug: "pan-model-123",
      sku: "PAN-123",
      short_description: "ظرفیت 2 لیتر",
      description: "بدنه با ضخامت 4 میلی‌متر",
    };
    const { container } = renderProduct("/products/pan-model-123/");

    expect(await screen.findByRole("heading", { name: "قابلمه مدل ۱۲۳" })).toBeTruthy();
    expect(container.querySelector(".product-detail__short").textContent).toBe("ظرفیت ۲ لیتر");
    expect(container.querySelector(".product-detail__description").textContent).toBe("بدنه با ضخامت ۴ میلی‌متر");
    expect(document.title).toContain("قابلمه مدل ۱۲۳");

    const jsonLd = JSON.parse(document.head.querySelector('script[id="product-jsonld"]')?.textContent || "{}");
    expect(jsonLd.name).toBe("قابلمه مدل 123");
    expect(jsonLd.sku).toBe("PAN-123");
    expect(jsonLd.url).toMatch(/\/products\/pan-model-123\/$/);
  });

  it("labels the product wishlist heart for assistive technology", async () => {
    const { container } = renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });
    expect(container.querySelector(".product-detail__buy .icon-btn[aria-label='افزودن به علاقه‌مندی‌ها']")).toBeTruthy();
  });

  it("shows an unclipped muted SKU below the image and preserves the machine-readable SKU", async () => {
    renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });

    const jsonLd = JSON.parse(
      document.head.querySelector('script[id="product-jsonld"]')?.textContent || "{}"
    );
    expect(jsonLd.sku).toBe("PAN-1");
    const sku = screen.getByText("PAN-۱").closest(".product-detail__sku");
    expect(sku.closest(".product-detail__gallery")).toBeTruthy();
    expect(sku.closest(".product-gallery__stage")).toBeNull();
  });


  it("uses collapsible description/specs after the purchase controls on phones", async () => {
    window.matchMedia = (query) => ({ ...originalMatchMedia(query), matches: query === "(max-width: 767px)" });
    const { container } = renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });
    const sections = container.querySelectorAll("details.product-detail__section");
    expect(sections.length).toBe(2);
    expect([...sections].every((section) => !section.open)).toBe(true);
    expect(sections[0].textContent).toContain("توضیحات کامل محصول");
    fireEvent.click(sections[0].querySelector("summary"));
    expect(sections[0].open).toBe(true);
    expect(container.querySelector(".product-detail__buy").compareDocumentPosition(sections[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("bounds the sticky gallery to the primary row and disables stickiness on phones", () => {
    const css = fs.readFileSync(path.resolve(__dirname, "../styles/storefront.css"), "utf8");
    expect(css).toMatch(/\.product-detail__body\s*\{[^}]*display: grid;[^}]*grid-template-columns: minmax\(0, \.9fr\) minmax\(0, 1\.1fr\)/);
    expect(css).toMatch(/\.product-detail__gallery\s*\{[^}]*position: sticky/);
    expect(css).toMatch(/@media \(max-width: 767px\)\s*\{[^}]*\}\s*\.product-detail__gallery\s*\{ position: static/);
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
