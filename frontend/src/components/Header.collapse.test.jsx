/*
 * The phone header's scroll behaviour. jsdom has no layout viewport, so the
 * CSS that paints the collapsed row is asserted straight from the authored
 * stylesheet (same source-audit pattern as the mobile/fixed-UI guards),
 * while this file drives the real component: the scroll direction, the
 * class names it publishes, the search icon that grows the field back, and
 * the measured heights the height transition needs.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import Header from "./Header.jsx";

const HERE = dirname(fileURLToPath(import.meta.url));
const CSS = readFileSync(join(HERE, "..", "styles", "storefront.css"), "utf8");

const originalAdapter = apiClient.defaults.adapter;

function renderHeader() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Header />
    </MemoryRouter>
  );
}

/** Move the (mockable) scroll position and announce it like a browser does. */
function scrollTo(y) {
  Object.defineProperty(window, "scrollY", { value: y, configurable: true });
  fireEvent.scroll(window);
}

/** jsdom reports 0 for every box; give the header a believable height. */
function stubHeaderHeight(headerHeight, innerHeight) {
  for (const [selector, height] of [
    [".site-header", headerHeight],
    [".site-header__inner", innerHeight],
  ]) {
    const node = document.querySelector(selector);
    if (node) Object.defineProperty(node, "offsetHeight", { configurable: true, get: () => height });
  }
}

beforeEach(() => {
  apiClient.defaults.adapter = async (config) => {
    if ((config.url || "").startsWith("/categories/tree/")) {
      return { data: { count: 0, next: null, previous: null, results: [] }, status: 200, statusText: "OK", headers: {}, config };
    }
    return originalAdapter(config);
  };
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, error: null });
  useCartStore.setState({
    cart: null,
    guestLines: [],
    guestProducts: {},
    guestVariants: {},
    guestHydration: "idle",
  });
});

afterEach(() => {
  cleanup();
  apiClient.defaults.adapter = originalAdapter;
  Object.defineProperty(window, "scrollY", { value: 0, configurable: true });
});

describe("phone header collapse on scroll", () => {
  it("keeps the full header at the top and folds it past 80px of scrolling down", () => {
    renderHeader();
    const header = document.querySelector(".site-header");
    expect(header.className).not.toContain("site-header--collapsed");

    scrollTo(40);
    expect(header.className).toContain("site-header--compact");
    expect(header.className).not.toContain("site-header--collapsed");

    scrollTo(120);
    expect(header.className).toContain("site-header--collapsed");
  });

  it("restores the full header when scrolling back up, even above the top", () => {
    renderHeader();
    const header = document.querySelector(".site-header");

    scrollTo(240);
    expect(header.className).toContain("site-header--collapsed");

    // Still deep in the page, but the shopper is coming back up.
    scrollTo(140);
    expect(header.className).not.toContain("site-header--collapsed");

    // ...and a second trip down folds it again.
    scrollTo(200);
    expect(header.className).toContain("site-header--collapsed");

    // Reaching the top always restores it.
    scrollTo(10);
    expect(header.className).not.toContain("site-header--collapsed");
  });

  it("ignores scroll jitter so the header never flickers between heights", () => {
    renderHeader();
    const header = document.querySelector(".site-header");

    scrollTo(300);
    expect(header.className).toContain("site-header--collapsed");

    // A 1px bounce (rubber-band, the tail of a smooth scroll) is not a
    // direction change.
    scrollTo(299);
    expect(header.className).toContain("site-header--collapsed");
    scrollTo(301);
    expect(header.className).toContain("site-header--collapsed");
  });

  it("grows the search field back into view from the collapsed row and focuses it", () => {
    renderHeader();
    const header = document.querySelector(".site-header");
    scrollTo(160);

    const toggle = document.querySelector(".site-header__search-toggle");
    expect(toggle).toBeTruthy();
    expect(toggle.getAttribute("aria-label")).toBe("نمایش جستجو");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.getAttribute("aria-controls")).toBe("site-header-search");
    expect(document.getElementById("site-header-search")).toBeTruthy();

    fireEvent.click(toggle);
    expect(header.className).toContain("site-header--searching");
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(document.activeElement).toBe(screen.getByLabelText("جستجوی محصول"));

    // Tapping it again folds the field away; the header stays collapsed.
    fireEvent.click(toggle);
    expect(header.className).not.toContain("site-header--searching");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });

  it("publishes the natural height the transition interpolates, but never while collapsed", async () => {
    const root = document.documentElement;
    renderHeader();
    stubHeaderHeight(245, 243);

    scrollTo(0);
    await waitFor(() => {
      expect(root.style.getPropertyValue("--site-header-height")).toBe("245px");
      expect(root.style.getPropertyValue("--header-natural-height")).toBe("243px");
    });

    // Collapsed: the current height keeps moving (sticky offsets follow),
    // but the natural height must stay the expanded one or the fold could
    // never animate back open.
    stubHeaderHeight(57, 55);
    scrollTo(200);
    await waitFor(() => expect(root.style.getPropertyValue("--site-header-height")).toBe("57px"));
    expect(root.style.getPropertyValue("--header-natural-height")).toBe("243px");
  });
});

describe("phone header collapse stylesheet", () => {
  it("transitions the inner's height between the measured and one-row heights", () => {
    expect(CSS).toMatch(/@media \(max-width: 767px\) \{[\s\S]*?\.site-header__inner \{\s*height: var\(--header-natural-height, auto\);\s*transition: height \.2s ease/);
    expect(CSS).toMatch(/\.site-header--collapsed \.site-header__inner \{\s*height: var\(--header-height-row\);\s*min-height: 0;/);
    expect(CSS).toMatch(/\.site-header--collapsed \.site-header__search-toggle \{ display: inline-grid; \}/);
    // Searching grows the inner back and stops clipping the suggestions list.
    expect(CSS).toMatch(/\.site-header--collapsed\.site-header--searching \.site-header__inner \{\s*height: auto;\s*overflow: visible;\s*\}/);
    expect(CSS).toMatch(/\.site-header--collapsed\.site-header--searching \.site-header__search \{ display: flex; \}/);
  });

  it("defines the one-row height and hides the toggle everywhere else", () => {
    const variables = readFileSync(join(HERE, "..", "styles", "variables.css"), "utf8");
    expect(variables).toMatch(/--header-height-row: 56px;/);
    expect(CSS).toMatch(/\.site-header__search-toggle \{\s*display: none;/);
  });

  it("hides only the controls that are not part of the one row", () => {
    const folded = [
      ".site-header--collapsed .site-header__search,",
      ".site-header--collapsed .site-header__nav,",
      ".site-header--collapsed .site-header__mega-trigger,",
      ".site-header--collapsed .site-header__actions .btn,",
      ".site-header--collapsed .site-header__actions .user-menu { display: none; }",
    ].join(" ");
    expect(CSS.replace(/\s+/g, " ")).toContain(folded);
    // The burger, the brand and the cart badge stay in the row.
    expect(CSS).not.toMatch(/\.site-header--collapsed \.site-header__(burger|brand|actions) \{ display: none/);
  });
});
