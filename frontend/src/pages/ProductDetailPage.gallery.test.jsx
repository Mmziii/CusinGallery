/**
 * Part S5 item 3: the product page really renders the gallery.
 *
 * ProductGallery.test.jsx covers the component's behaviour; this file
 * covers the WIRING, so the gallery cannot silently disappear from the
 * product page again (the main image and the thumbnail row used to be
 * an inline block here).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import ProductDetailPage from "./ProductDetailPage";

const priceInfo = (price) => ({
  price,
  compare_at_price: null,
  discount_percentage: 0,
  is_on_sale: false,
  discount_amount: 0,
});

const image = (id, suffix) => ({
  id,
  image: `/media/products/pan-${suffix}.jpg`,
  alt_text: `تصویر ${suffix}`,
  is_primary: id === 1,
  ordering: id,
  webp_400: `/media/products/pan-${suffix}-400.webp`,
  webp_800: `/media/products/pan-${suffix}-800.webp`,
  webp_1200: `/media/products/pan-${suffix}-1200.webp`,
});

const BASE = {
  id: 1,
  name: "قابلمه گرانیتی",
  slug: "pan",
  sku: "PAN-1",
  short_description: "قابلمه گرانیتی با کف ضخیم",
  description: "توضیحات کامل",
  category: { id: 1, name: "قابلمه", slug: "pots" },
  brand: { id: 2, name: "یونیک", slug: "unique" },
  price_info: priceInfo(850000),
  stock_status: "in_stock",
  is_in_stock: true,
  is_featured: false,
  is_new: false,
  is_best_seller: false,
  variants: [],
  specifications: [],
  related_products: [],
  complements: [],
};

const THREE_IMAGES = {
  ...BASE,
  images: [image(1, "a"), image(2, "b"), image(3, "c")],
  primary_image: image(1, "a"),
};
const ONE_IMAGE = { ...BASE, images: [image(1, "a")], primary_image: image(1, "a") };

const originalAdapter = apiClient.defaults.adapter;

function serve(data) {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (url === "/products/pan/") {
      return { data, status: 200, statusText: "OK", headers: {}, config };
    }
    if (/^\/reviews\//.test(url)) {
      return { data: { count: 0, next: null, previous: null, results: [] }, status: 200, statusText: "OK", headers: {}, config };
    }
    return originalAdapter(config);
  };
}

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    if ((config.url || "") !== "/products/pan/") return originalAdapter(config);
    return { data: THREE_IMAGES, status: 200, statusText: "OK", headers: {}, config };
  };
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
afterEach(cleanup);

function renderProduct() {
  const { container } = render(
    <MemoryRouter initialEntries={["/products/pan/"]}>
      <Routes>
        <Route path="/products/:slug/" element={<ProductDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
  return container;
}

describe("ProductDetailPage gallery wiring (Part S5 item 3)", () => {
  it("renders the shared gallery with one thumbnail per image", async () => {
    serve(THREE_IMAGES);
    const container = renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });

    await waitFor(() => {
      expect(container.querySelector('[role="tablist"]')).not.toBeNull();
    });
    expect(container.querySelectorAll(".thumb").length).toBe(3);
    expect(container.querySelector(".thumb--active")).not.toBeNull();
  });

  it("switches the main image when a thumbnail is selected", async () => {
    serve(THREE_IMAGES);
    const container = renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });
    await waitFor(() => expect(container.querySelectorAll(".thumb").length).toBe(3));

    fireEvent.click(container.querySelectorAll(".thumb")[2]);

    await waitFor(() => {
      const active = container.querySelectorAll(".product-gallery__layer--active img");
      expect(active[active.length - 1].getAttribute("srcset") || active[active.length - 1].getAttribute("src"))
        .toContain("pan-c");
    });
  });

  it("shows no thumbnail row for a product with a single image", async () => {
    serve(ONE_IMAGE);
    const container = renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });

    await waitFor(() => {
      expect(container.querySelector(".product-gallery__layer--active img")).not.toBeNull();
    });
    expect(container.querySelector(".thumb")).toBeNull();
  });
});
