/**
 * Part S4 item 1: "no image" preview everywhere.
 *
 * One shared placeholder (light warm-grey field with the brand mark in
 * olive at ~35% opacity, same aspect ratio as real images) is used
 * wherever an image can be missing or broken. These tests cover the gaps
 * the owner reported:
 *   (b) the secondary hover image on a product card hides itself silently;
 *   (c) brand tiles: tile_image, else the brand logo on a tinted field,
 *       else the placeholder;
 *   (d) hero slides and banners, home category tiles, plus the surfaces
 *       that already went through SmartImage (wishlist, suggestions,
 *       order/invoice thumbnails, complements, recently viewed).
 *
 * The "raw <img> outside the component" rule is enforced separately in
 * src/assets.guard.test.js.
 */
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import BrandTiles from "../components/BrandTiles";
import ProductCard from "../components/ProductCard";
import SmartImage from "../components/SmartImage";
import apiClient from "../services/apiClient";
import Home from "../pages/Home";
import WishlistPage from "../pages/WishlistPage";

const priceInfo = (price) => ({
  price,
  compare_at_price: null,
  discount_percentage: 0,
  is_on_sale: false,
  discount_amount: 0,
});

const product = (overrides = {}) => ({
  id: 1,
  name: "قابلمه گرانیتی",
  slug: "pan",
  price: 850000,
  price_info: priceInfo(850000),
  stock_status: "in_stock",
  is_in_stock: true,
  primary_image: null,
  images: [],
  ...overrides,
});

afterEach(cleanup);

describe("SmartImage accepts a bare URL string (Category.image, Brand.logo)", () => {
  it("renders the real image for a string url", () => {
    const { container } = render(<SmartImage image="/media/categories/pots.jpg" alt="قابلمه" />);
    expect(container.querySelector("img").getAttribute("src")).toBe("/media/categories/pots.jpg");
  });

  it("renders the shared placeholder for an empty/absent value", () => {
    for (const value of [null, undefined, ""]) {
      cleanup();
      const { container } = render(<SmartImage image={value} alt="قابلمه" />);
      expect(container.querySelector("img")).toBeNull();
      expect(container.querySelector(".img-placeholder__mark")).not.toBeNull();
    }
  });

  it("falls back to the placeholder when a string url is broken", () => {
    const { container } = render(<SmartImage image="/media/gone.jpg" alt="از دست رفته" />);
    fireEvent.error(container.querySelector("img"));
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector(".img-placeholder")).not.toBeNull();
  });
});

describe("ProductCard hover image (gap b)", () => {
  it("hides the secondary image silently when it fails to load", () => {
    const card = product({
      primary_image: { image: "/media/primary.jpg" },
      images: [
        { id: 1, image: "/media/primary.jpg", is_primary: true },
        { id: 2, image: "/media/secondary.jpg", is_primary: false },
      ],
    });
    const { container } = render(
      <MemoryRouter>
        <ProductCard product={card} />
      </MemoryRouter>
    );

    const alt = container.querySelector(".product-card__img--alt");
    expect(alt).not.toBeNull();
    fireEvent.error(alt);
    expect(container.querySelector(".product-card__img--alt")).toBeNull();
    // The primary image is still there, and no placeholder took its place
    // (the hover layer is decorative only).
    expect(container.querySelector(".product-card__img--main")).not.toBeNull();
    expect(container.querySelectorAll(".img-placeholder").length).toBe(0);
  });
});

describe("Brand tiles (gap c)", () => {
  function serveBrands(results) {
    apiClient.defaults.adapter = async (config) => {
      if (/^\/brands\//.test(config.url || "")) {
        return { data: { count: results.length, next: null, previous: null, results }, status: 200, statusText: "OK", headers: {}, config };
      }
      return { data: {}, status: 200, statusText: "OK", headers: {}, config };
    };
  }

  it("uses the tile image when there is one", async () => {
    serveBrands([
      { id: 1, name: "یونیک", slug: "unique", logo: null, tile_image: { image: "/media/tile.jpg" } },
    ]);
    const { container } = render(
      <MemoryRouter>
        <BrandTiles />
      </MemoryRouter>
    );
    await waitFor(() => expect(container.querySelector(".brand-tile__media img")).not.toBeNull());
    expect(container.querySelector(".brand-tile__media img").getAttribute("src")).toBe("/media/tile.jpg");
    expect(container.querySelector(".brand-tile__media--tinted")).toBeNull();
  });

  it("shows the brand logo on a tinted field when there is no tile image", async () => {
    serveBrands([
      { id: 2, name: "بدون کاشی", slug: "no-tile", logo: "/media/logo.png", tile_image: null },
    ]);
    const { container } = render(
      <MemoryRouter>
        <BrandTiles />
      </MemoryRouter>
    );
    await waitFor(() => expect(container.querySelector(".brand-tile__media img")).not.toBeNull());
    expect(container.querySelector(".brand-tile__media img").getAttribute("src")).toBe("/media/logo.png");
    expect(container.querySelector(".brand-tile__media--tinted")).not.toBeNull();
  });

  it("shows the shared placeholder when the brand has neither", async () => {
    serveBrands([{ id: 3, name: "بی‌تصویر", slug: "none", logo: null, tile_image: null }]);
    const { container } = render(
      <MemoryRouter>
        <BrandTiles />
      </MemoryRouter>
    );
    await waitFor(() => expect(container.querySelector(".img-placeholder")).not.toBeNull());
    expect(container.querySelector(".brand-tile__media img")).toBeNull();
    expect(container.querySelector(".img-placeholder__mark")).not.toBeNull();
  });
});

describe("Home page hero and category tiles (gap a + d)", () => {
  const originalAdapter = apiClient.defaults.adapter;

  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter;
  });

  it("renders the shared placeholder for a category without an image, never an empty span", async () => {
    apiClient.defaults.adapter = async (config) => {
      const url = config.url || "";
      if (url.startsWith("/categories/tree")) {
        return {
          data: {
            count: 2,
            next: null,
            previous: null,
            results: [
              { id: 1, name: "قابلمه", slug: "pots", image: null, ordering: 0, product_count: 1, children: [] },
              { id: 2, name: "بلور", slug: "glass", image: "/media/categories/glass.jpg", ordering: 1, product_count: 1, children: [] },
            ],
          },
          status: 200, statusText: "OK", headers: {}, config,
        };
      }
      if (/^\/banners\//.test(url)) {
        return { data: { count: 0, next: null, previous: null, results: [] }, status: 200, statusText: "OK", headers: {}, config };
      }
      return { data: { count: 0, next: null, previous: null, results: [] }, status: 200, statusText: "OK", headers: {}, config };
    };

    const { container } = render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );

    await waitFor(() => expect(container.querySelectorAll(".category-card").length).toBe(2));
    const cards = container.querySelectorAll(".category-card");
    // The imageless category has a placeholder, not an empty span.
    expect(cards[0].querySelector(".img-placeholder__mark")).not.toBeNull();
    expect(cards[0].querySelector("img")).toBeNull();
    // The other one renders its real image.
    expect(cards[1].querySelector("img").getAttribute("src")).toBe("/media/categories/glass.jpg");
  });

  it("shows the placeholder for a hero slide whose image is missing or broken", async () => {
    apiClient.defaults.adapter = async (config) => {
      const url = config.url || "";
      if (/^\/banners\/daily-deals/.test(url)) {
        return { data: { count: 0, next: null, previous: null, server_now: new Date().toISOString(), results: [] }, status: 200, statusText: "OK", headers: {}, config };
      }
      if (/^\/banners\//.test(url)) {
        return {
          data: {
            count: 2,
            next: null,
            previous: null,
            results: [
              { id: 1, title: "بدون تصویر", subtitle: "", image: null, cta_text: "", cta_url: "" },
              { id: 2, title: "تصویر شکسته", subtitle: "", image: "/media/gone.jpg", cta_text: "", cta_url: "" },
            ],
          },
          status: 200, statusText: "OK", headers: {}, config,
        };
      }
      return { data: { count: 0, next: null, previous: null, results: [] }, status: 200, statusText: "OK", headers: {}, config };
    };

    const { container } = render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );

    await waitFor(() => expect(container.querySelectorAll(".hero__slide").length).toBe(2));
    const slides = container.querySelectorAll(".hero__slide");
    expect(slides[0].querySelector(".img-placeholder__mark")).not.toBeNull();
    // The broken one starts as an <img> and degrades to the placeholder.
    const brokenImg = slides[1].querySelector("img");
    expect(brokenImg).not.toBeNull();
    fireEvent.error(brokenImg);
    await waitFor(() => expect(slides[1].querySelector(".img-placeholder__mark")).not.toBeNull());
  });
});

describe("Wishlist page without images (gap d)", () => {
  it("renders the shared placeholder instead of a broken image", async () => {
    // The wishlist API returns { id, product, is_available } rows.
    apiClient.defaults.adapter = async (config) => {
      if (/^\/wishlist\//.test(config.url || "")) {
        return {
          data: {
            count: 1,
            next: null,
            previous: null,
            results: [{ id: 5, product: product({ primary_image: null }), is_available: true }],
          },
          status: 200, statusText: "OK", headers: {}, config,
        };
      }
      return { data: {}, status: 200, statusText: "OK", headers: {}, config };
    };
    const { container } = render(
      <MemoryRouter>
        <WishlistPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(container.querySelector(".img-placeholder")).not.toBeNull());
    expect(container.querySelector(".img-placeholder__mark")).not.toBeNull();
  });
});
