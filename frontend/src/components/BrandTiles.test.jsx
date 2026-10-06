/**
 * Featured brand tiles tests (Part R2): tiles render from the
 * /brands/?is_featured=true endpoint, link to /shop/?brand=<slug>, and the
 * section disappears when nothing is featured.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import BrandTiles from "./BrandTiles";

const FEATURED = {
  count: 2,
  next: null,
  previous: null,
  results: [
    { id: 1, name: "یونیک", slug: "unique", logo: null, is_featured: true, display_order: 0, tile_image: null },
    { id: 2, name: "کریستال پارس", slug: "crystal-pars", logo: null, is_featured: true, display_order: 1, tile_image: null },
  ],
};

let featuredResults = FEATURED;
let requestedParams = null;
const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (/\/brands\//.test(url)) {
      requestedParams = config.params || {};
      return { data: featuredResults, status: 200, statusText: "OK", headers: {}, config };
    }
    return originalAdapter(config);
  };
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
afterEach(() => {
  cleanup();
  requestedParams = null;
});

describe("BrandTiles", () => {
  it("renders featured brands as tiles linking to the brand shop filter", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <BrandTiles />
      </MemoryRouter>
    );

    const tile = await screen.findByText("یونیک");
    expect(requestedParams).toMatchObject({ is_featured: "true" });
    const link = tile.closest("a");
    expect(link.getAttribute("href")).toBe("/shop/?brand=unique");
    expect(screen.getByText("کریستال پارس").closest("a").getAttribute("href")).toBe(
      "/shop/?brand=crystal-pars"
    );
  });

  it("renders nothing when no brand is featured", async () => {
    featuredResults = { count: 0, next: null, previous: null, results: [] };
    const { container } = render(
      <MemoryRouter initialEntries={["/"]}>
        <BrandTiles />
      </MemoryRouter>
    );
    await waitFor(() => expect(requestedParams).not.toBeNull());
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(container.querySelector(".brand-tiles")).toBeNull();
    featuredResults = FEATURED;
  });
});
