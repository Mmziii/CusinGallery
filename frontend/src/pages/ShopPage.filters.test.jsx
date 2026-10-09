/**
 * Part S5 item 7: filtering is a transition, not a page reload.
 *
 * These tests pin the behaviour that makes the change visible:
 *  - while a new page is in flight the PREVIOUS results stay on screen,
 *    dimmed (`shop__results--loading`) and marked `aria-busy`; the spinner
 *    is reserved for the very first load, so the grid never blinks away;
 *  - when the new page lands, every card replays the fade+rise entrance
 *    with a ~20ms/card stagger that is CAPPED (no card waits more than
 *    MAX_STAGGER * 20ms);
 *  - the price inputs are debounced (~300ms) so typing a number does not
 *    fire one request per keystroke, while blur still applies instantly;
 *  - filter groups collapse with the grid-template-rows technique (the
 *    inputs stay in the DOM, they are only visually collapsed) and the
 *    mobile filter drawer toggles with an aria-expanded state.
 *
 * The CSS durations/easing live in storefront.css; what can be asserted
 * from jsdom is the markup/state contract these animations hang off.
 */
import fs from "node:fs";
import path from "node:path";

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import ShopPage from "./ShopPage";

const originalAdapter = apiClient.defaults.adapter;

const makeProduct = (id, name) => ({
  id,
  name,
  slug: `product-${id}`,
  stock_status: "in_stock",
  is_new: false,
  brand: null,
  primary_image: null,
  images: [],
  price_info: { price: 100000 + id, compare_at_price: null, discount_percentage: 0 },
});

const PAGE_A = {
  count: 2,
  next: null,
  previous: null,
  results: [makeProduct(1, "کالای اول"), makeProduct(2, "کالای دوم")],
};
const PAGE_B = {
  count: 1,
  next: null,
  previous: null,
  results: [makeProduct(3, "کالای تازه")],
};

let productRequests = [];
// Queue of deferred product responses: when non-empty the adapter hands
// back a promise that the test resolves by hand, which is what keeps the
// "loading" window open long enough to assert against.
let pendingResponses = [];
let deferredMode = false;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (/\/products\/facets\//.test(url)) {
      return { data: { count: 0, next: null, previous: null, results: [] }, status: 200, statusText: "OK", headers: {}, config };
    }
    if (/^\/categories\//.test(url)) {
      return { data: { count: 0, next: null, previous: null, results: [] }, status: 200, statusText: "OK", headers: {}, config };
    }
    if (/^\/brands\//.test(url)) {
      const data = {
        count: 1,
        next: null,
        previous: null,
        results: [
          { id: 1, name: "یونیک", slug: "unique", logo: null, tile_image: null, is_featured: true, display_order: 0 },
        ],
      };
      return { data, status: 200, statusText: "OK", headers: {}, config };
    }
    if (/\/products\//.test(url)) {
      productRequests.push(config.params || {});
      if (deferredMode) {
        return new Promise((resolve) => pendingResponses.push(resolve));
      }
      return { data: PAGE_A, status: 200, statusText: "OK", headers: {}, config };
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
  pendingResponses = [];
  deferredMode = false;
});

function renderShop(query = "") {
  return render(
    <MemoryRouter initialEntries={[`/shop/${query}`]}>
      <ShopPage />
    </MemoryRouter>
  );
}

async function resolvePending(data) {
  // The adapter is async, so the deferred resolver lands a microtask later.
  await waitFor(() => expect(pendingResponses.length).toBeGreaterThan(0));
  const next = pendingResponses.shift();
  await act(async () => {
    next({ data, status: 200, statusText: "OK", headers: {}, config: {} });
    await Promise.resolve();
  });
}

const results = () => document.querySelector(".shop__results");
const cells = () => [...document.querySelectorAll(".product-grid__cell")];

describe("shop page filter transitions (Part S5 item 7)", () => {
  it("keeps the previous results visible, dimmed and aria-busy while the next page loads", async () => {
    renderShop();
    await screen.findByText("کالای اول");
    expect(screen.queryByText("در حال دریافت محصولات…")).toBeNull();

    deferredMode = true;
    fireEvent.click(screen.getByLabelText("فقط کالاهای موجود"));

    await waitFor(() => expect(results().getAttribute("aria-busy")).toBe("true"));
    expect(results().className).toContain("shop__results--loading");
    // The old cards are still rendered -- the grid does not blank out.
    expect(screen.getByText("کالای اول")).toBeTruthy();
    expect(screen.getByText("کالای دوم")).toBeTruthy();
    // ... and no spinner is shown for a filter change.
    expect(screen.queryByText("در حال دریافت محصولات…")).toBeNull();

    await resolvePending(PAGE_B);
    await screen.findByText("کالای تازه");
    await waitFor(() => expect(results().getAttribute("aria-busy")).toBeNull());
    expect(results().className).not.toContain("shop__results--loading");
    expect(screen.queryByText("کالای اول")).toBeNull();
    expect(productRequests.some((params) => params.in_stock === "true")).toBe(true);
  });

  it("shows the spinner only before the first page arrives", async () => {
    deferredMode = true;
    renderShop();
    expect(screen.getByText("در حال دریافت محصولات…")).toBeTruthy();
    expect(results()).toBeNull();

    await waitFor(() => expect(pendingResponses.length).toBeGreaterThan(0));
    await resolvePending(PAGE_A);
    await screen.findByText("کالای اول");
    expect(screen.queryByText("در حال دریافت محصولات…")).toBeNull();
  });

  it("replays the card entrance with a 20ms stagger capped at the tenth card", async () => {
    deferredMode = true;
    renderShop();

    const many = {
      count: 13,
      next: null,
      previous: null,
      results: Array.from({ length: 13 }, (_, index) => makeProduct(100 + index, `کالای ${index}`)),
    };
    await resolvePending(many);
    await screen.findByText("کالای 0");

    const delays = cells().map((cell) => cell.style.animationDelay);
    expect(delays[0]).toBe("0ms");
    expect(delays[1]).toBe("20ms");
    expect(delays[2]).toBe("40ms");
    // Cap: from the 11th card on the delay stops growing.
    expect(delays[10]).toBe("200ms");
    expect(delays[12]).toBe("200ms");
    expect(new Set(delays).size).toBeLessThan(13);
  });

  it("debounces the price inputs (~300ms) and applies them immediately on blur", async () => {
    renderShop();
    await screen.findByText("کالای اول");
    const before = productRequests.length;

    const min = screen.getByLabelText("کمترین قیمت");
    fireEvent.change(min, { target: { value: "1" } });
    fireEvent.change(min, { target: { value: "12" } });
    fireEvent.change(min, { target: { value: "123" } });
    // Nothing yet: the three keystrokes are still inside the debounce window.
    expect(productRequests.length).toBe(before);
    // The input itself stays responsive (controlled local state).
    expect(min.value).toBe("123");

    await waitFor(() => expect(productRequests.some((p) => p.min_price === "123")).toBe(true));
    // One request for the whole burst, not one per keystroke.
    expect(productRequests.filter((p) => p.min_price).length).toBe(1);

    // Blur does not wait for the timer: the next value is applied at once.
    fireEvent.change(min, { target: { value: "456" } });
    fireEvent.blur(min);
    await waitFor(() => expect(productRequests.some((p) => p.min_price === "456")).toBe(true));
  });

  it("collapses a filter group with grid-template-rows while keeping its inputs in the DOM", async () => {
    renderShop();
    await screen.findByText("کالای اول");

    const toggle = screen.getByRole("button", { name: /دسته‌بندی/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const group = toggle.closest(".filter-group");
    expect(group.className).not.toContain("filter-group--collapsed");

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(group.className).toContain("filter-group--collapsed");
    // The select is only visually collapsed -- DOM and options survive, so
    // reopening the group (or a keyboard user tabbing through) sees the
    // same control.
    const collapsedSelect = document.querySelector(".filter-group--collapsed select");
    expect(collapsedSelect).toBeTruthy();
    expect(collapsedSelect.options.length).toBeGreaterThan(0);
    expect(document.querySelector(".filter-group--collapsed .filter-group__body-inner")).toBeTruthy();

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
  });

  it("opens and closes the mobile filter drawer with an aria-expanded toggle", async () => {
    renderShop();
    await screen.findByText("کالای اول");

    const toggle = screen.getByRole("button", { name: /^فیلترها$/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    const panel = document.getElementById("shop-filters");
    expect(panel.className).not.toContain("shop__filters--open");

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(panel.className).toContain("shop__filters--open");

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    // The panel is still in the DOM (CSS does the hiding).
    expect(document.getElementById("shop-filters")).toBeTruthy();
  });

  it("animates an active-filter chip in with the shared entrance", async () => {
    renderShop("?brand=unique");
    const chip = await screen.findByText(/برند: یونیک/);
    const chipElement = chip.closest(".shop__chip");
    expect(chipElement).toBeTruthy();
    // The CSS hook the scale+fade entrance hangs off.
    expect(chipElement.className).toContain("shop__chip");

    const before = productRequests.length;
    fireEvent.click(screen.getByLabelText("حذف فیلتر برند"));
    await waitFor(() => expect(productRequests.length).toBeGreaterThan(before));
    expect(productRequests.at(-1).brand).toBeUndefined();
  });

  it("expresses the transition with short transform/opacity animations and honours reduced motion", () => {
    const css = fs.readFileSync(path.resolve(__dirname, "../styles/storefront.css"), "utf8");
    // One easing, 180-280ms, transform/opacity only.
    expect(css).toContain("cubic-bezier(0.2, 0.8, 0.2, 1)");
    expect(css).toMatch(/filter-card-in 240ms cubic-bezier\(0\.2, 0\.8, 0\.2, 1\)/);
    expect(css).toMatch(/filter-chip-in 200ms cubic-bezier\(0\.2, 0\.8, 0\.2, 1\)/);
    expect(css).toMatch(/@keyframes filter-card-in \{\s*from \{ opacity: 0; transform: translateY\(8px\); \}/);
    expect(css).toMatch(/@keyframes filter-chip-in \{\s*from \{ opacity: 0; transform: scale\(\.92\); \}/);
    // The grid-template-rows technique, shared by the groups and the drawer.
    expect(css).toContain("grid-template-rows 220ms cubic-bezier(0.2, 0.8, 0.2, 1)");
    expect(css).toContain(".filter-group--collapsed .filter-group__body { grid-template-rows: 0fr; visibility: hidden; }");
    expect(css).toContain(".shop__filters--open { grid-template-rows: 1fr; visibility: visible; }");
    // And the whole motion set collapses to instant for reduced motion.
    const motionBlock = css.slice(css.indexOf("PART S5 item 7"));
    expect(motionBlock).toContain(".product-grid__cell, .shop__chip { animation: none; }");
  });
});
