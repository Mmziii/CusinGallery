/**
 * Part S4 item 2: the product page's share image (og:image) and JSON-LD.
 *
 * The reported bug: og:image was built as `${SITE_ORIGIN}${product.
 * primary_image}`, but primary_image is an OBJECT (and may be missing from
 * the detail response), so the tag never pointed at a real image. These
 * tests render the real page against a fake API and read document.head.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import { SITE_ORIGIN } from "../hooks/usePageMeta";
import ProductDetailPage from "./ProductDetailPage";

const priceInfo = (price) => ({
  price,
  compare_at_price: null,
  discount_percentage: 0,
  is_on_sale: false,
  discount_amount: 0,
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

const WITH_IMAGES = {
  ...BASE,
  images: [
    {
      id: 10,
      image: "/media/products/pan.jpg",
      alt_text: "قابلمه",
      is_primary: true,
      ordering: 0,
      webp_400: "/media/products/pan-400.webp",
      webp_800: "/media/products/pan-800.webp",
      webp_1200: "/media/products/pan-1200.webp",
    },
  ],
  primary_image: {
    id: 10,
    image: "/media/products/pan.jpg",
    webp_400: "/media/products/pan-400.webp",
    webp_800: "/media/products/pan-800.webp",
    webp_1200: "/media/products/pan-1200.webp",
  },
};

// The detail response may omit primary_image entirely (documented in the
// report); the first gallery image is still usable.
const IMAGES_ONLY = { ...BASE, primary_image: null, images: WITH_IMAGES.images };
const NO_IMAGES = { ...BASE, primary_image: null, images: [] };

const originalAdapter = apiClient.defaults.adapter;

function serve(data) {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (url === "/products/pan/") {
      return { data, status: 200, statusText: "OK", headers: {}, config };
    }
    if (/^\/reviews\//.test(url)) {
      return { data: { count: 0, results: [] }, status: 200, statusText: "OK", headers: {}, config };
    }
    return originalAdapter(config);
  };
}

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    if ((config.url || "") !== "/products/pan/") return originalAdapter(config);
    return { data: WITH_IMAGES, status: 200, statusText: "OK", headers: {}, config };
  };
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
afterEach(() => {
  cleanup();
  document.head.querySelectorAll('meta[property="og:image"]').forEach((tag) => tag.remove());
  document.head.querySelectorAll('script[id="product-jsonld"]').forEach((tag) => tag.remove());
});

function renderProduct() {
  return render(
    <MemoryRouter initialEntries={["/products/pan/"]}>
      <Routes>
        <Route path="/products/:slug/" element={<ProductDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

const ogImage = () =>
  document.head.querySelector('meta[property="og:image"]')?.getAttribute("content") || null;
const jsonLd = () => {
  const raw = document.head.querySelector('script[id="product-jsonld"]')?.textContent;
  return raw ? JSON.parse(raw) : null;
};

describe("ProductDetailPage share image (Part S4 item 2)", () => {
  it("uses the product's first image as an absolute URL, preferring the largest WebP variant", async () => {
    serve(WITH_IMAGES);
    renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });

    await waitFor(() => {
      expect(ogImage()).toBe(`${SITE_ORIGIN}/media/products/pan-1200.webp`);
    });
    // Never the old object-ish URL.
    expect(ogImage()).not.toContain("object");
  });

  it("falls back to the first gallery image when the detail response omits primary_image", async () => {
    serve(IMAGES_ONLY);
    renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });

    await waitFor(() => {
      expect(ogImage()).toBe(`${SITE_ORIGIN}/media/products/pan-1200.webp`);
    });
  });

  it("uses the brand placeholder when the product has no image", async () => {
    serve(NO_IMAGES);
    renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });

    await waitFor(() => {
      expect(ogImage()).toBe(`${SITE_ORIGIN}/brand/og-placeholder.png`);
    });
  });

  it("emits JSON-LD Product with the same absolute image, price and availability", async () => {
    serve(NO_IMAGES);
    renderProduct();
    await screen.findByRole("heading", { name: "قابلمه گرانیتی" });

    await waitFor(() => {
      const data = jsonLd();
      expect(data).toBeTruthy();
      expect(data["@type"]).toBe("Product");
      expect(data.name).toBe("قابلمه گرانیتی");
      expect(data.image).toEqual([`${SITE_ORIGIN}/brand/og-placeholder.png`]);
      expect(data.sku).toBe("PAN-1");
      expect(data.offers.price).toBe("850000");
      expect(data.offers.priceCurrency).toBe("IRT");
      expect(data.offers.availability).toBe("https://schema.org/InStock");
      expect(data.brand).toEqual({ "@type": "Brand", name: "یونیک" });
    });
  });
});
