/**
 * Shop page attribute-facet tests (Part R5 item 8): the sidebar renders
 * one checkbox group per attribute from /products/facets/, ticking a
 * value puts attr_<slug>=value in the URL (reload/share-safe) and the
 * product query is refetched with that param; arriving with an attr
 * param preselects the checkbox and shows an active-filter chip.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import ShopPage from "./ShopPage";

const FACETS = {
  results: [
    {
      slug: "rang",
      name: "رنگ",
      values: [
        { value: "قرمز", count: 2 },
        { value: "آبی", count: 1 },
      ],
    },
  ],
};

let productRequests = [];
const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (/\/products\/facets\//.test(url)) {
      return { data: FACETS, status: 200, statusText: "OK", headers: {}, config };
    }
    if (/\/products\//.test(url)) {
      productRequests.push(config.params || {});
      return {
        data: { count: 0, next: null, previous: null, results: [] },
        status: 200, statusText: "OK", headers: {}, config,
      };
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

describe("shop page attribute facets", () => {
  it("renders facet checkboxes with counts", async () => {
    render(
      <MemoryRouter initialEntries={["/shop/"]}>
        <ShopPage />
      </MemoryRouter>
    );
    expect(await screen.findByText("رنگ")).toBeTruthy();
    expect(await screen.findByText("قرمز")).toBeTruthy();
    expect(await screen.findByText("(2)")).toBeTruthy();
  });

  it("ticking a value updates the URL and the product query", async () => {
    render(
      <MemoryRouter initialEntries={["/shop/"]}>
        <ShopPage />
      </MemoryRouter>
    );
    const checkbox = (await screen.findByText("قرمز")).closest("label").querySelector("input");
    fireEvent.click(checkbox);

    await waitFor(() =>
      expect(productRequests.some((params) => params.attr_rang === "قرمز")).toBe(true)
    );
    // the active-filter chip reflects the facet's display name
    expect(await screen.findByText(/رنگ: قرمز/)).toBeTruthy();
  });

  it("arriving with an attr param preselects the checkbox and shows a chip", async () => {
    render(
      <MemoryRouter initialEntries={["/shop/?attr_rang=%D9%82%D8%B1%D9%85%D8%B2"]}>
        <ShopPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(productRequests.length).toBeGreaterThan(0));
    expect(productRequests[0]).toMatchObject({ attr_rang: "قرمز" });

    const checkbox = (await screen.findByText("قرمز")).closest("label").querySelector("input");
    expect(checkbox.checked).toBe(true);
    expect(await screen.findByText(/رنگ: قرمز/)).toBeTruthy();
  });
});
