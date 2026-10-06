/**
 * Shop page brand-param tests (Part R2): arriving at /shop/?brand=<slug>
 * (e.g. from a brand tile) must filter the product query by that brand,
 * preselect it in the brand filter, and show an active-filter chip.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import ShopPage from "./ShopPage";

const BRANDS = {
  count: 1,
  next: null,
  previous: null,
  results: [{ id: 1, name: "یونیک", slug: "unique", logo: null, is_featured: true, display_order: 0, tile_image: null }],
};

let productRequests = [];
const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (/\/products\//.test(url)) {
      productRequests.push(config.params || {});
      return {
        data: { count: 0, next: null, previous: null, results: [] },
        status: 200, statusText: "OK", headers: {}, config,
      };
    }
    if (/\/brands\//.test(url)) {
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
  productRequests = [];
});

describe("shop page brand param", () => {
  it("filters products by the brand in the URL and shows the active chip", async () => {
    render(
      <MemoryRouter initialEntries={["/shop/?brand=unique"]}>
        <ShopPage />
      </MemoryRouter>
    );

    await waitFor(() => expect(productRequests.length).toBeGreaterThan(0));
    expect(productRequests[0]).toMatchObject({ brand: "unique" });

    // active filter chip with the brand's display name
    expect(await screen.findByText(/برند: یونیک/)).toBeTruthy();

    // the sidebar brand select (second select) mirrors the URL param
    const brandSelect = document.querySelectorAll("select")[1];
    expect(brandSelect.value).toBe("unique");
  });
});
