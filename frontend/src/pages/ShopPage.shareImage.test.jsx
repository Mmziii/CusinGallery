/**
 * Part S4 item 2: category and brand pages set their own og:image.
 * Before, /shop/?category=<slug> and /shop/?brand=<slug> always used the
 * site-wide default image. Now the category image (or the brand tile, with
 * the brand logo as fallback, then the shared placeholder) is used, as an
 * absolute URL.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import { SITE_ORIGIN } from "../hooks/usePageMeta";
import ShopPage from "./ShopPage";

const CATEGORIES = {
  count: 2,
  next: null,
  previous: null,
  results: [
    { id: 1, name: "قابلمه", slug: "pots", image: "/media/categories/pots.jpg", parent: null, parent_slug: null, ordering: 0, product_count: 2, description: "" },
    { id: 2, name: "بلور", slug: "glass", image: null, parent: null, parent_slug: null, ordering: 1, product_count: 1, description: "" },
  ],
};
const BRANDS = {
  count: 2,
  next: null,
  previous: null,
  results: [
    { id: 1, name: "یونیک", slug: "unique", logo: null, is_featured: true, display_order: 0, tile_image: { image: "/media/brands/unique-tile.jpg", webp_400: null, webp_800: "/media/brands/unique-tile-800.webp", webp_1200: "/media/brands/unique-tile-1200.webp" } },
    { id: 2, name: "بدون تصویر", slug: "plain", logo: "/media/brands/plain-logo.png", is_featured: false, display_order: 1, tile_image: null },
  ],
};

const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (/^\/categories\//.test(url)) {
      return { data: CATEGORIES, status: 200, statusText: "OK", headers: {}, config };
    }
    if (/^\/brands\//.test(url)) {
      return { data: BRANDS, status: 200, statusText: "OK", headers: {}, config };
    }
    return originalAdapter(config);
  };
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
afterEach(() => {
  cleanup();
  document.head.querySelectorAll('meta[property="og:image"]').forEach((tag) => tag.remove());
});

function renderShop(query) {
  return render(
    <MemoryRouter initialEntries={[`/shop/${query}`]}>
      <ShopPage />
    </MemoryRouter>
  );
}

const ogImage = () =>
  document.head.querySelector('meta[property="og:image"]')?.getAttribute("content") || null;

describe("Shop page share image (Part S4 item 2)", () => {
  it("uses the selected category image as an absolute URL", async () => {
    renderShop("?category=pots");
    await waitFor(() => {
      expect(ogImage()).toBe(`${SITE_ORIGIN}/media/categories/pots.jpg`);
    });
  });

  it("uses the brand tile image (largest variant) for a brand page", async () => {
    renderShop("?brand=unique");
    await waitFor(() => {
      expect(ogImage()).toBe(`${SITE_ORIGIN}/media/brands/unique-tile-1200.webp`);
    });
  });

  it("falls back to the brand logo, then to the shared placeholder", async () => {
    renderShop("?brand=plain");
    await waitFor(() => {
      expect(ogImage()).toBe(`${SITE_ORIGIN}/media/brands/plain-logo.png`);
    });

    cleanup();
    renderShop("?category=glass");
    await waitFor(() => {
      expect(ogImage()).toBe(`${SITE_ORIGIN}/brand/og-placeholder.png`);
    });
  });

  it("leaves the site-wide default image in place for an unfiltered shop page", async () => {
    renderShop("");
    await screen.findByRole("heading", { name: "فروشگاه" });
    expect(ogImage()).toBeNull();
  });
});
