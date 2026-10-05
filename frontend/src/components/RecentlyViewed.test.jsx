/**
 * Part R5 item 10: the «اخیراً دیده‌اید» widget. Verifies it hydrates
 * browser-local ids through the existing ?ids= filter, keeps the
 * most-recent-first order regardless of the API's reply order, drops
 * unavailable products silently, and renders nothing when empty.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import { RECENT_KEY } from "../utils/recentlyViewed";
import RecentlyViewed from "./RecentlyViewed";

const row = (id, name) => ({
  id,
  name,
  slug: `p-${id}`,
  short_description: "",
  category: null,
  brand: null,
  price_info: { price: 1000 * id, compare_at_price: null, discount_percentage: 0, is_on_sale: false, discount_amount: 0 },
  primary_image: null,
  stock_status: "in_stock",
  is_in_stock: true,
  is_featured: false,
  is_new: false,
  is_best_seller: false,
});

let lastParams = null;
const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (url === "/products/") {
      lastParams = config.params || {};
      const ids = String(lastParams.ids || "")
        .split(",")
        .map(Number)
        .filter(Boolean);
      // The "server" only knows products 1 and 3; anything else
      // (e.g. 99) is silently absent, exactly like the real API.
      const known = ids.filter((id) => id === 1 || id === 3);
      return {
        // Reply in REVERSE order to prove the widget re-sorts by the
        // stored most-recent-first order.
        data: { count: known.length, next: null, previous: null, results: [...known].reverse().map((id) => row(id, `کالا ${id}`)) },
        status: 200, statusText: "OK", headers: {}, config,
      };
    }
    return originalAdapter(config);
  };
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
beforeEach(() => {
  localStorage.clear();
  lastParams = null;
});
afterEach(() => cleanup());

function renderWidget() {
  return render(
    <MemoryRouter>
      <RecentlyViewed />
    </MemoryRouter>
  );
}

describe("recently viewed widget", () => {
  it("renders nothing with an empty local list (no API call)", async () => {
    const { container } = renderWidget();
    expect(container.querySelector(".recently-viewed")).toBeNull();
    expect(lastParams).toBeNull();
  });

  it("hydrates ids through the ?ids= filter in stored order", async () => {
    localStorage.setItem(RECENT_KEY, JSON.stringify([3, 1, 99]));
    renderWidget();

    expect(await screen.findByText("اخیراً دیده‌اید")).toBeTruthy();
    expect(lastParams).toMatchObject({ ids: "3,1,99" });

    // 99 is absent server-side -> dropped silently; order stays 3 then 1.
    expect(screen.queryByText("کالا 99")).toBeNull();
    const cards = screen.getAllByText(/^کالا \d+$/);
    expect(cards.map((node) => node.textContent)).toEqual(["کالا 3", "کالا 1"]);
  });

  it("renders nothing when every stored id is unavailable", async () => {
    localStorage.setItem(RECENT_KEY, JSON.stringify([99, 98]));
    const { container } = renderWidget();
    // Wait until the hydration request actually ran, then confirm the
    // section still renders nothing.
    await waitFor(() => expect(lastParams).not.toBeNull());
    expect(screen.queryByText("اخیراً دیده‌اید")).toBeNull();
    expect(container.querySelector(".recently-viewed")).toBeNull();
  });
});
