/*
 * The phone header's scroll behaviour.
 *
 * jsdom has no layout viewport, so the CSS that paints the collapsed row is
 * asserted straight from the authored stylesheet (same source-audit pattern
 * as the mobile/fixed-UI guards), while this file drives the real component:
 * the scroll hysteresis (80px down / 24px up / always open at the top), the
 * class names it publishes, the measured heights the height transition
 * needs -- which must NEVER be taken from the folded or compact header --
 * and the search icon that grows the field back in place.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import Header from "./Header.jsx";

const HERE = dirname(fileURLToPath(import.meta.url));
const CSS = readFileSync(join(HERE, "..", "styles", "storefront.css"), "utf8");

const originalAdapter = apiClient.defaults.adapter;

/** Resolves after the component's rAF-throttled pass has run. */
function nextFrame() {
  return new Promise((resolve) => {
    if (window.requestAnimationFrame) {
      window.requestAnimationFrame(() => setTimeout(resolve, 0));
    } else {
      setTimeout(resolve, 25);
    }
  });
}

/** Move the (mockable) scroll position and announce it like a browser does. */
async function scrollTo(y) {
  Object.defineProperty(window, "scrollY", { value: y, configurable: true });
  await act(async () => {
    fireEvent.scroll(window);
    await nextFrame();
  });
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

function renderHeader() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Header />
      <LocationProbe />
    </MemoryRouter>
  );
}

/** jsdom reports 0 for every box; give the inner a believable height. */
function stubInnerHeight({ box, content }) {
  const inner = document.querySelector(".site-header__inner");
  Object.defineProperty(inner, "offsetHeight", { configurable: true, get: () => box });
  Object.defineProperty(inner, "scrollHeight", { configurable: true, get: () => content });
}

function naturalHeight() {
  return document.documentElement.style.getPropertyValue("--header-natural-height");
}

/** Capturing ResizeObserver: the component observes the expanded inner. */
class MockResizeObserver {
  static instances = [];

  constructor(callback) {
    this.callback = callback;
    this.elements = [];
    MockResizeObserver.instances.push(this);
  }

  observe(element) {
    this.elements.push(element);
  }

  unobserve() {}

  disconnect() {}

  trigger() {
    this.callback(this.elements.map((target) => ({ target })), this);
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
  MockResizeObserver.instances = [];
  window.ResizeObserver = MockResizeObserver;
});

afterEach(() => {
  cleanup();
  apiClient.defaults.adapter = originalAdapter;
  Object.defineProperty(window, "scrollY", { value: 0, configurable: true });
  document.documentElement.style.removeProperty("--header-natural-height");
  document.documentElement.style.removeProperty("--site-header-height");
});

describe("phone header collapse on scroll", () => {
  it("stays open at the top and folds only after 80px of downward travel", async () => {
    renderHeader();
    const header = document.querySelector(".site-header");
    await act(async () => {
      await nextFrame();
    });
    expect(header.className).not.toContain("site-header--collapsed");

    await scrollTo(40);
    expect(header.className).toContain("site-header--compact");
    expect(header.className).not.toContain("site-header--collapsed");

    await scrollTo(79);
    expect(header.className).not.toContain("site-header--collapsed");

    await scrollTo(120);
    expect(header.className).toContain("site-header--collapsed");
  });

  it("expands again after 24px of upward scroll, and always at the very top", async () => {
    renderHeader();
    const header = document.querySelector(".site-header");

    await scrollTo(300);
    expect(header.className).toContain("site-header--collapsed");

    // Deliberate swipe up: the full header comes back while still deep in
    // the page -- the bug was that it never did.
    await scrollTo(276);
    expect(header.className).not.toContain("site-header--collapsed");

    // ...and a second trip down folds it again.
    await scrollTo(300);
    expect(header.className).toContain("site-header--collapsed");

    // Reaching the top (<= 10px) always restores it, whatever the travel.
    await scrollTo(6);
    expect(header.className).not.toContain("site-header--collapsed");
    await scrollTo(0);
    expect(header.className).not.toContain("site-header--collapsed");
    expect(header.className).not.toContain("site-header--compact");
  });

  it("ignores scroll jitter so the header never flickers between heights", async () => {
    renderHeader();
    const header = document.querySelector(".site-header");

    await scrollTo(300);
    expect(header.className).toContain("site-header--collapsed");

    // A few 1-2px bounces (rubber-band, the tail of a smooth scroll) are not
    // the 24px of upward travel that re-opens the header.
    await scrollTo(299);
    expect(header.className).toContain("site-header--collapsed");
    await scrollTo(301);
    expect(header.className).toContain("site-header--collapsed");
    await scrollTo(297);
    expect(header.className).toContain("site-header--collapsed");
    await scrollTo(303);
    expect(header.className).toContain("site-header--collapsed");
  });

  it("grows the search field back into place and focuses it, without navigating", async () => {
    renderHeader();
    const header = document.querySelector(".site-header");
    await scrollTo(160);
    expect(header.className).toContain("site-header--collapsed");

    const toggle = document.querySelector(".site-header__search-toggle");
    expect(toggle).toBeTruthy();
    expect(toggle.getAttribute("type")).toBe("button");
    expect(toggle.getAttribute("aria-label")).toBe("نمایش جستجو");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.getAttribute("aria-controls")).toBe("site-header-search");
    expect(document.getElementById("site-header-search")).toBeTruthy();
    // The icon must not be a link to /shop/ -- it opens the field in place.
    expect(toggle.closest("a")).toBeNull();

    fireEvent.click(toggle);
    expect(header.className).toContain("site-header--searching");
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(document.activeElement).toBe(screen.getByLabelText("جستجوی محصول"));

    // No navigation happened: the storefront stays exactly where it was.
    expect(screen.getByTestId("location").textContent).toBe("/");

    // Tapping it again folds the field away; the header stays collapsed.
    fireEvent.click(toggle);
    expect(header.className).not.toContain("site-header--searching");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });
});

describe("natural header height measurement", () => {
  it("publishes the expanded content height once the header is at rest", async () => {
    renderHeader();
    stubInnerHeight({ box: 243, content: 243 });
    await waitFor(() => expect(naturalHeight()).toBe("243px"));
  });

  it("never publishes a height measured while compact, folded or animating", async () => {
    renderHeader();
    stubInnerHeight({ box: 243, content: 243 });
    await waitFor(() => expect(naturalHeight()).toBe("243px"));
    const observer = MockResizeObserver.instances.at(-1);
    expect(observer.elements).toContain(document.querySelector(".site-header__inner"));

    // Compact but still expanded (scrollY > 24): the box is shorter.
    stubInnerHeight({ box: 58, content: 58 });
    await scrollTo(40);
    await act(async () => {
      observer.trigger();
      await nextFrame();
    });
    expect(naturalHeight()).toBe("243px");

    // Folded to the one row: the content is one row tall -- definitely not
    // the natural height. A ResizeObserver pass here must be ignored.
    stubInnerHeight({ box: 56, content: 56 });
    await scrollTo(200);
    await act(async () => {
      observer.trigger();
      await nextFrame();
    });
    expect(naturalHeight()).toBe("243px");

    // Back at the top the header expands; the fold's height transition
    // starts. offsetHeight is interpolated now -- neither height -- so the
    // pass skips it instead of pinning the header to a partial value.
    await scrollTo(0);
    const inner = document.querySelector(".site-header__inner");
    const start = new Event("transitionstart");
    Object.defineProperty(start, "propertyName", { value: "height" });
    inner.dispatchEvent(start);
    stubInnerHeight({ box: 120, content: 120 });
    await act(async () => {
      observer.trigger();
      await nextFrame();
    });
    expect(naturalHeight()).toBe("243px");

    // At rest and expanded again, a fresh measurement is accepted.
    const end = new Event("transitionend");
    Object.defineProperty(end, "propertyName", { value: "height" });
    stubInnerHeight({ box: 244, content: 244 });
    inner.dispatchEvent(end);
    await waitFor(() => expect(naturalHeight()).toBe("244px"));
  });

  it("re-measures on resize and drops back to auto while it does", async () => {
    renderHeader();
    stubInnerHeight({ box: 243, content: 243 });
    await waitFor(() => expect(naturalHeight()).toBe("243px"));

    stubInnerHeight({ box: 258, content: 258 });
    act(() => {
      fireEvent(window, new Event("orientationchange"));
    });
    // Dropping the variable lets CSS fall back to `height: auto` -- the
    // content can never be clipped while the new value is measured.
    expect(naturalHeight()).toBe("");
    await waitFor(() => expect(naturalHeight()).toBe("258px"));
  });

  it("keeps --site-header-height on the real rendered height", async () => {
    renderHeader();
    const header = document.querySelector(".site-header");
    Object.defineProperty(header, "offsetHeight", { configurable: true, get: () => 245 });
    stubInnerHeight({ box: 243, content: 243 });
    await waitFor(() =>
      expect(document.documentElement.style.getPropertyValue("--site-header-height")).toBe("245px")
    );

    Object.defineProperty(header, "offsetHeight", { configurable: true, get: () => 57 });
    await scrollTo(220);
    await waitFor(() =>
      expect(document.documentElement.style.getPropertyValue("--site-header-height")).toBe("57px")
    );
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

  it("keeps exactly the menu, logo, search icon and cart badge in the row", () => {
    const folded = [
      ".site-header--collapsed .site-header__search,",
      ".site-header--collapsed .site-header__nav,",
      ".site-header--collapsed .site-header__mega-trigger,",
      ".site-header--collapsed .site-header__actions .btn,",
      ".site-header--collapsed .site-header__actions .user-menu { display: none; }",
    ].join(" ");
    expect(CSS.replace(/\s+/g, " ")).toContain(folded);
    // The brand NAME folds too; the logo stays.
    expect(CSS.replace(/\s+/g, " ")).toContain(".site-header--collapsed .site-header__brand-name { display: none; }");
    // The burger, the brand and the cart badge stay in the row.
    expect(CSS).not.toMatch(/\.site-header--collapsed \.site-header__(burger|brand|actions) \{ display: none/);
  });

  it("keeps the header in the normal flow so it can never cover the page", () => {
    expect(CSS).toMatch(/\.site-header \{\s*position: sticky; top: 0;/);
    // The sticky header is not overlaid by an absolutely positioned copy of
    // itself: its box is the flow box, so the content below always starts
    // under the real rendered height.
    expect(CSS).not.toMatch(/\.site-header \{[^}]*position: fixed/);
  });
});
