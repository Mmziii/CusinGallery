/**
 * Part R5 item 10: the «اخیراً دیده‌اید» widget. Verifies it hydrates
 * browser-local ids through the existing ?ids= filter, keeps the
 * most-recent-first order regardless of the API's reply order, drops
 * unavailable products silently, and renders nothing when empty.
 */
import fs from "node:fs";
import path from "node:path";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

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
let allKnown = false;
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
      const known = ids.filter((id) => allKnown || id === 1 || id === 3);
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
  allKnown = false;
});
afterEach(() => cleanup());

function renderWidget(props = {}) {
  return render(
    <MemoryRouter>
      <RecentlyViewed {...props} />
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
    const cards = screen.getAllByText(/^کالا [۰-۹]+$/);
    expect(cards.map((node) => node.textContent)).toEqual(["کالا ۳", "کالا ۱"]);
  });


  it("shows ten prior products in one row, excluding the current product even after a reload", async () => {
    allKnown = true;
    localStorage.setItem(RECENT_KEY, JSON.stringify([11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]));
    const { container } = renderWidget({ excludeId: 11 });
    await screen.findByText("اخیراً دیده‌اید");
    expect(lastParams.ids).toBe("10,9,8,7,6,5,4,3,2,1");
    expect(container.querySelectorAll(".recently-viewed__track > .recently-viewed__item").length).toBe(10);
    expect(container.querySelector(".product-grid")).toBeNull();
    expect(screen.queryByText("کالا ۱۱")).toBeNull();
  });

  it("shows only the scroll arrows that can move, and scrolls in the correct RTL direction", async () => {
    localStorage.setItem(RECENT_KEY, JSON.stringify([3, 1]));
    const { container } = renderWidget();
    await screen.findByText("اخیراً دیده‌اید");
    const track = container.querySelector(".recently-viewed__track");
    Object.defineProperties(track, { clientWidth: { value: 500 }, scrollWidth: { value: 1500 } });
    track.scrollBy = vi.fn();
    fireEvent.resize(window);
    expect(screen.queryByRole("button", { name: "محصولات قبلی" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "محصولات بعدی" }));
    expect(track.scrollBy).toHaveBeenCalledWith({ left: -450, behavior: "smooth" });
    track.scrollLeft = -1000;
    fireEvent.scroll(track);
    expect(screen.queryByRole("button", { name: "محصولات بعدی" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "محصولات قبلی" }));
    expect(track.scrollBy).toHaveBeenLastCalledWith({ left: 450, behavior: "smooth" });
    fireEvent.keyDown(track, { key: "ArrowRight" });
    expect(track.scrollBy).toHaveBeenLastCalledWith({ left: 450, behavior: "smooth" });
  });

  it("never wraps cards; uses 5/4/3 desktop-to-tablet slots and a 2.3-card phone peek", () => {
    const css = fs.readFileSync(path.resolve(__dirname, "../styles/storefront.css"), "utf8");
    expect(css).toMatch(/\.recently-viewed__track\s*\{[^}]*display: flex; flex-wrap: nowrap/);
    expect(css).toMatch(/\.recently-viewed__track\s*\{[^}]*scroll-snap-type: x mandatory/);
    for (const [width, slots] of [[1279, 4], [1023, 3], [767, 2.3]]) {
      expect(css).toMatch(new RegExp(`@media \\(max-width: ${width}px\\)\\s*\\{\\s*\\.recently-viewed__track\\s*\\{[^}]* / ${slots}\\)`));
    }
    expect(css).toContain("--recent-card-size: calc((100% - 4 * var(--space-3)) / 5)");
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
