/**
 * Audit 19 item 1: the compact phone card.
 *
 * At ≤767px every product grid is two columns wide, so the card switches to
 * a different shape: square image with a light field and `object-fit:
 * contain`, badges as small chips, wishlist heart on the opposite corner, a
 * 2-line name, a reserved 1-line brand line, the crossed-out old price next
 * to a bold final price pinned to the card's bottom, a round cart-plus
 * button (36px) instead of the full-width text button, and «موجود شد خبرم
 * کن» as a small text link when the product is out of stock.
 *
 * The desktop markup must stay exactly as it was.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProductCard from "./ProductCard";
import useCartStore from "../store/useCartStore";
import useWishlistStore from "../store/useWishlistStore";

const toast = vi.fn();
vi.mock("../utils/toast", () => ({
  toast: (...args) => toast(...args),
  onToast: () => () => {},
}));

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CSS = fs.readFileSync(path.join(HERE, "..", "styles", "storefront.css"), "utf8").replace(/\s+/g, " ");
const originalMatchMedia = window.matchMedia;

/** Pretend the browser is a 375px phone (or back to a desktop). */
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

const LONG_NAME =
  "قابلمه استیل سه‌لایه با درب شیشه‌ای مقاوم و دسته عایق حرارت مناسب همه اجاق‌ها";

function makeProduct(overrides = {}) {
  return {
    id: 7,
    name: LONG_NAME,
    slug: "pan",
    stock_status: "in_stock",
    is_new: false,
    brand: { id: 2, name: "یونیک", slug: "unique" },
    primary_image: null,
    images: [],
    price_info: { price: 12345000, compare_at_price: 15000000, discount_percentage: 18 },
    ...overrides,
  };
}

const renderCard = (product) =>
  render(
    <MemoryRouter>
      <ProductCard product={product} />
    </MemoryRouter>
  );

beforeEach(() => {
  toast.mockClear();
  setViewport(true);
  useCartStore.setState({ addItem: async () => ({ success: true }) });
  useWishlistStore.setState({ items: [], toggle: async () => {} });
});

afterEach(() => {
  cleanup();
  window.matchMedia = originalMatchMedia;
});

describe("ProductCard compact mode (phones)", () => {
  it("uses the compact layout with a round 36px add button instead of the text button", () => {
    const { container } = renderCard(makeProduct());

    expect(container.querySelector(".product-card--compact")).toBeTruthy();
    const add = screen.getByRole("button", { name: "افزودن به سبد" });
    expect(add.className).toContain("product-card__add-icon");
    // ... and NOT the desktop text button.
    expect(container.querySelector(".product-card__footer .btn")).toBeNull();
  });

  it("shows the discount chip on the image, the struck-through old price and the bold final price", () => {
    const { container } = renderCard(makeProduct());

    const badge = container.querySelector(".product-card__badges .badge--sale");
    expect(badge).toBeTruthy();
    expect(badge.closest(".product-card__media")).toBeTruthy();
    expect(badge.textContent).toBe("۱۸٪");

    // Old price struck through + final price, both Persian digits, inside the
    // bottom row (so prices line up across a row of cards).
    const compare = container.querySelector(".product-card__footer .price__compare");
    const current = container.querySelector(".product-card__footer .price__current");
    expect(compare.textContent).toBe("۱۵٬۰۰۰٬۰۰۰");
    expect(current.textContent).toBe("۱۲٬۳۴۵٬۰۰۰");
  });

  it("derives a compact discount badge from compare-at pricing", () => {
    const { container } = renderCard(makeProduct({
      price_info: { price: 80000, compare_at_price: 100000, discount_percentage: 0 },
    }));
    expect(container.querySelector(".product-card__badges .badge--sale").textContent).toBe("۲۰٪");
  });

  it("changes the wishlist accessible label when the product is saved", () => {
    useWishlistStore.setState({ items: [{ product: { id: 7 } }], toggle: async () => {} });
    renderCard(makeProduct());
    expect(screen.getByRole("button", { name: "حذف از علاقه‌مندی‌ها" })).toBeTruthy();
  });

  it("reserves the brand line even when the product has no brand", () => {
    const { container } = renderCard(makeProduct({ brand: null }));
    const brand = container.querySelector(".product-card__brand");
    expect(brand).toBeTruthy();
    expect(brand.textContent.trim()).toBe("");
  });

  it("keeps the wishlist heart on the image, opposite the badges", () => {
    const { container } = renderCard(makeProduct());
    const heart = container.querySelector(".product-card__media-wrap .product-card__heart");
    expect(heart).toBeTruthy();
    expect(heart.getAttribute("aria-label")).toBe("افزودن به علاقه‌مندی‌ها");
    // Clicking the heart must not navigate to the product.
    expect(heart.closest("a")).toBeNull();
  });

  it("toasts «به سبد اضافه شد» with a «مشاهده سبد» action after adding", async () => {
    useCartStore.setState({ addItem: async () => ({ success: true }) });
    renderCard(makeProduct());

    fireEvent.click(screen.getByRole("button", { name: "افزودن به سبد" }));

    await waitFor(() => expect(toast).toHaveBeenCalledTimes(1));
    expect(toast.mock.calls[0][0]).toBe("به سبد اضافه شد");
    expect(toast.mock.calls[0][2]).toEqual({ label: "مشاهده سبد", to: "/cart/" });
  });

  it("offers «موجود شد خبرم کن» as a small link and no add button when out of stock", () => {
    const { container } = renderCard(makeProduct({ stock_status: "out_of_stock" }));

    const notify = container.querySelector(".product-card__notify");
    expect(notify.textContent).toBe("موجود شد خبرم کن");
    expect(notify.getAttribute("href")).toBe("/products/pan/");
    expect(container.querySelector(".product-card__add-icon")).toBeNull();
    expect(container.querySelector(".badge--oos")).toBeTruthy();
  });

  it("labels «تعداد محدود» as a chip on the image corner", () => {
    const { container } = renderCard(makeProduct({ stock_status: "low_stock" }));
    const chip = container.querySelector(".badge--low");
    expect(chip.textContent).toBe("تعداد محدود");
    expect(chip.closest(".product-card__badges").closest(".product-card__media")).toBeTruthy();
  });

  it("keeps the desktop card untouched at ≥768px", () => {
    setViewport(false);
    const { container } = renderCard(makeProduct());

    expect(container.querySelector(".product-card--compact")).toBeNull();
    expect(container.querySelector(".product-card__footer .btn").textContent).toBe("افزودن به سبد");
    expect(container.querySelector(".product-card__heart")).toBeNull();
  });
});

describe("compact card CSS contract", () => {
  it("is a 2-column phone grid with 8px gaps and 12px page padding", () => {
    expect(CSS).toMatch(
      /@media \(max-width: 767px\) \{ \.container \{ padding-inline: 12px; \} \.product-grid, \.related-grid, \.wishlist-grid, \.complements__grid \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); gap: 8px; \}/
    );
    expect(CSS).toMatch(
      /@media \(min-width: 768px\) and \(max-width: 1023px\) \{ \.product-grid, \.related-grid, \.wishlist-grid, \.complements__grid \{ grid-template-columns: repeat\(3, minmax\(0, 1fr\)\);/
    );
  });

  it("squares the image with contain fit on a light field and hides hover layers", () => {
    expect(CSS).toMatch(/\.product-card__media \{ aspect-ratio: 1 \/ 1; background: #f3f1e8; \}/);
    // The contain fit is declared for every image shape the media box can
    // hold (plain <img>, the <picture> wrapper SmartImage renders, and the
    // shared placeholder) inside the phone media query.
    expect(CSS).toMatch(
      /\.product-card__media img, \.product-card__media picture img, \.product-card__media \.img-placeholder, \.product-card__media picture \{ object-fit: contain; \}/
    );
    expect(CSS).toMatch(/\.product-card__img--alt \{ display: none; \}/);
    expect(CSS).toMatch(/\.product-card__name \{[^}]*font-size: 13px;/);
    expect(CSS).toMatch(/\.product-card__brand \{ font-size: 11px;/);
    expect(CSS).toMatch(/\.product-card__add-icon \{[^}]*width: 36px; height: 36px;/);
    expect(CSS).toMatch(/\.product-card__heart \{[^}]*width: 32px; height: 32px;/);
  });

  it("keeps the daily deal card balanced with a prominent image", () => {
    expect(CSS).toMatch(/\.deals-grid \{[^}]*max-width: 860px;[^}]*margin-inline: auto;/);
    expect(CSS).toMatch(/\.deal-card \{[^}]*display: flex;[^}]*flex-direction: row;/);
    expect(CSS).toMatch(/\.deal-card__media \{[^}]*flex: 0 0 60%;/);
    expect(CSS).toMatch(/\.deal-card__media.*object-fit: contain;/);
    expect(CSS).toMatch(/\.countdown__value \{[^}]*font-variant-numeric: tabular-nums;/);
    expect(CSS).toMatch(/\.countdown__label \{/);
  });
});
