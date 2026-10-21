/*
 * PR 21 — the fixes from the live test of PR 20 that touch Header.jsx and
 * the header/deals/checkout stylesheet.
 *
 * The stuck flip pin is the real bug: at 375px the folded pill with its
 * revealed search row is 128px and the EXPANDED header is also 128px, so
 * the FLIP pinned `height:128px; overflow:hidden` inline, no height
 * transition ran, `transitionstart` never fired, no watchdog was armed and
 * the pin stayed forever — clipping the search suggestions. Two defences
 * are asserted here: equal heights pin nothing at all, and every pin that
 * IS taken is released by a fallback timer even when no transition event
 * ever arrives.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import apiClient from "../services/apiClient";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import { loadStyles } from "../test/cssCascade";
import Header from "./Header.jsx";

const HERE = dirname(fileURLToPath(import.meta.url));
const CSS = readFileSync(join(HERE, "..", "styles", "storefront.css"), "utf8");
const MEDIA = loadStyles().media;
const mediaCss = (params) =>
  MEDIA.filter((entry) => entry.params === params)
    .map((entry) => entry.css)
    .join("\n")
    .replace(/\s+/g, " ");

const originalAdapter = apiClient.defaults.adapter;
const originalMatchMedia = window.matchMedia;

/** Phones only: `(max-width: 767px)` matches, every other query does not. */
function setPhoneViewport(phone) {
  window.matchMedia = (query) => ({
    matches: Boolean(phone && query.includes("max-width: 767px")),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

/**
 * Run one animation frame. Deliberately rAF-based (not a setTimeout race):
 * these tests fake setTimeout so the fallback timer is under their control,
 * while the header's scroll pass stays rAF-throttled and real.
 */
async function frame() {
  await act(async () => {
    await new Promise((resolve) => {
      if (window.requestAnimationFrame) window.requestAnimationFrame(() => resolve());
      setTimeout(resolve, 0);
    });
    await Promise.resolve();
  });
}

/** Move the (mockable) scroll position and let the rAF pass run. */
async function scrollTo(y) {
  Object.defineProperty(window, "scrollY", { value: y, configurable: true });
  fireEvent.scroll(window);
  await frame();
  await frame();
}

function renderHeader() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Header />
    </MemoryRouter>
  );
}

/** jsdom reports 0 for every box; give the inner a believable height. */
function stubInnerHeight(box) {
  const inner = document.querySelector(".site-header__inner");
  Object.defineProperty(inner, "offsetHeight", { configurable: true, get: () => box });
  Object.defineProperty(inner, "scrollHeight", { configurable: true, get: () => box });
  return inner;
}

const innerElement = () => document.querySelector(".site-header__inner");
const naturalHeight = () => document.documentElement.style.getPropertyValue("--header-natural-height");

/** The browser's transitionend for the inner's height. */
function heightSettled(inner = innerElement()) {
  const event = new Event("transitionend");
  Object.defineProperty(event, "propertyName", { value: "height" });
  inner.dispatchEvent(event);
}

/** Publish `value` as the measured natural height before the test drives
 *  the fold (the measure pass only reads the expanded, at-rest header). */
async function measureNaturalHeight(value) {
  stubInnerHeight(value);
  for (let i = 0; i < 3; i += 1) await frame();
  expect(naturalHeight()).toBe(`${value}px`);
}

beforeEach(() => {
  setPhoneViewport(true);
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
  // Only the timers the fallback release uses are faked: requestAnimationFrame
  // stays real, so the scroll pass and the measure pass keep running.
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  apiClient.defaults.adapter = originalAdapter;
  window.matchMedia = originalMatchMedia;
  Object.defineProperty(window, "scrollY", { value: 0, configurable: true });
  document.documentElement.style.removeProperty("--header-natural-height");
  document.documentElement.style.removeProperty("--site-header-height");
});

describe("the phone fold's FLIP pin (PR 21 stuck-pin fix)", () => {
  it("leaves no inline height/overflow when the target already is the current height", async () => {
    // The live repro: folded pill + revealed search = 128px, expanded
    // header = 128px. 128 over 128 animates nothing, so transitionstart
    // never fired and the pin (overflow:hidden included) stuck forever.
    renderHeader();
    await measureNaturalHeight(128);

    const header = document.querySelector(".site-header");
    const inner = stubInnerHeight(128);

    // Fold, and settle that pin the way the browser would...
    await scrollTo(220);
    expect(header.className).toContain("site-header--collapsed");
    heightSettled(inner);
    expect(inner.getAttribute("style") || "").toBe("");

    // ...then expand into an already-128px box: nothing to animate, so
    // NOTHING may be left inline (a pinned overflow would clip the
    // suggestion list the shopper is typing into).
    await scrollTo(0);
    expect(header.className).not.toContain("site-header--collapsed");
    expect(inner.style.height).toBe("");
    expect(inner.style.overflow).toBe("");
    expect(inner.getAttribute("style") || "").toBe("");
  });

  it("releases a pin that no transition event ever clears (fallback timer)", async () => {
    renderHeader();
    await measureNaturalHeight(124);

    const header = document.querySelector(".site-header");
    const inner = stubInnerHeight(124);

    // Fold from 124 to the one-row pill, then settle it cleanly.
    await scrollTo(220);
    expect(header.className).toContain("site-header--collapsed");
    heightSettled(inner);
    expect(inner.getAttribute("style") || "").toBe("");

    // Expand from a 56px row: the pin really is taken...
    stubInnerHeight(56);
    await scrollTo(0);
    expect(header.className).not.toContain("site-header--collapsed");
    expect(inner.style.height).toBe("124px");
    expect(inner.style.overflow).toBe("hidden");

    // ...and NO transitionstart/transitionend ever arrives (a cancelled or
    // unstarted transition). The fallback timer must clear it anyway.
    act(() => {
      vi.advanceTimersByTime(460);
    });
    expect(inner.style.height).toBe("");
    expect(inner.style.overflow).toBe("");
  });
});

describe("Escape in the revealed pill search (PR 21)", () => {
  it("clears the text first, then closes the row and returns focus to the icon", async () => {
    renderHeader();
    const header = document.querySelector(".site-header");
    await scrollTo(160);
    expect(header.className).toContain("site-header--collapsed");

    const toggle = document.querySelector(".site-header__search-toggle");
    fireEvent.click(toggle);
    expect(header.className).toContain("site-header--searching");

    const input = screen.getByLabelText("جستجوی محصول");
    expect(document.activeElement).toBe(input);

    // 1) With text: Escape clears the field and the row stays open.
    fireEvent.change(input, { target: { value: "کارد" } });
    expect(input.value).toBe("کارد");
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input.value).toBe("");
    expect(header.className).toContain("site-header--searching");

    // 2) Empty: Escape closes the revealed row and hands the focus back.
    fireEvent.keyDown(input, { key: "Escape" });
    expect(header.className).not.toContain("site-header--searching");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(toggle);
    // The header is still the folded pill, not the expanded two rows.
    expect(header.className).toContain("site-header--collapsed");
  });
});

describe("PR 21 stylesheet contracts", () => {
  it("opens the account panel to the right of the trigger at <= 1099px", () => {
    const iconOnly = mediaCss("(max-width: 1099px)");
    const panel = iconOnly.match(/\.user-menu__panel \{[^}]*\}/);
    expect(panel).toBeTruthy();
    // The trigger sits on the physical LEFT edge; anchoring the panel to
    // its left edge (left: 0, right: auto) opens it back into the viewport.
    expect(panel[0]).toContain("left: 0;");
    expect(panel[0]).toContain("right: auto;");
    expect(panel[0]).toContain("max-width: calc(100vw - 16px);");
    // Wide screens keep the original placement.
    expect(CSS.replace(/\s+/g, " ")).toContain(
      ".user-menu__panel { position: absolute; top: calc(100% + 6px); inset-inline-start: 0;"
    );
  });

  it("makes the header search input fill its container at every width", () => {
    const flat = CSS.replace(/\s+/g, " ");
    const form = flat.match(/\.site-header__search form \{[^}]*\}/)[0];
    expect(form).toContain("flex: 1 1 auto;");
    expect(form).toContain("min-width: 0;");
    expect(form).toContain("width: 100%;");
    const input = flat.match(/\.site-header__search input \{[^}]*\}/)[0];
    expect(input).toContain("flex: 1 1 auto;");
    expect(input).toContain("min-width: 0;");
    // The submit button keeps its own size.
    expect(flat.match(/\.site-header__search \.btn \{[^}]*\}/)[0]).toContain("flex: none;");
  });

  it("keeps «پیشنهاد امروز» on one line and drops the timer to its own row", () => {
    const flat = CSS.replace(/\s+/g, " ");
    const rules = (selector) =>
      [...flat.matchAll(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} \\{[^}]*\\}`, "g"))].map(
        (match) => match[0]
      );
    expect(rules(".deals-mobile__title").some((rule) => rule.includes("white-space: nowrap;"))).toBe(true);
    expect(rules(".deals-mobile__header").some((rule) => rule.includes("flex-wrap: wrap;"))).toBe(true);
    const narrow = mediaCss("(max-width: 480px)");
    const timer = narrow.match(/\.deals-mobile__header > \.countdown \{[^}]*\}/);
    expect(timer).toBeTruthy();
    expect(timer[0]).toContain("flex: 1 1 100%;");
    expect(timer[0]).toContain("margin-inline-start: 0;");
  });

  it("paints the native search clear button in the brand colours at 44px", () => {
    const flat = CSS.replace(/\s+/g, " ");
    const cancel = flat.match(/input\[type="search"\]::-webkit-search-cancel-button \{[^}]*\}/)[0];
    expect(cancel).toContain("width: 44px;");
    expect(cancel).toContain("height: 44px;");
    expect(cancel).toContain("-webkit-appearance: none;");
    expect(cancel).toContain("background-color: var(--search-clear-color, var(--brand-ink));");
    // Gold on the green header, ink on white surfaces.
    expect(flat).toContain(".site-header__search input { --search-clear-color: var(--brand-gold); }");
    expect(flat).toContain('input[type="search"] { --search-clear-color: var(--brand-ink); }');
  });

  it("caps the checkout review thumbnail at 64px on phones", () => {
    const phone = mediaCss("(max-width: 767px)");
    expect(phone).toContain(".checkout__review-item > picture img");
    expect(phone).toMatch(/\.checkout__review-item > picture img,[\s\S]*?width: 64px;/);
    expect(phone).toMatch(/\.checkout__review-item > picture img,[\s\S]*?max-width: 64px;/);
  });
});
