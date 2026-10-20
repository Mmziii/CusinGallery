/*
 * The header's scroll behaviour (PR 19: floating pill + constant outer box).
 *
 * jsdom has no layout viewport, so the CSS that paints the collapsed row is
 * asserted straight from the authored stylesheet (same source-audit pattern
 * as the mobile/fixed-UI guards), while this file drives the real component:
 * the compact hysteresis (on past 40px, off below 8px), the phone fold
 * (80px down / 24px up / always open at the top), the 350ms post-toggle
 * delta lock that breaks the scroll-anchoring feedback loop, the spacer that
 * owns the phone header's flow height, the measured heights -- which must
 * NEVER be taken from the folded or compact header -- and the search icon
 * that grows the field back in place.
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
import { loadStyles } from "../test/cssCascade";
import Header from "./Header.jsx";

const HERE = dirname(fileURLToPath(import.meta.url));
const CSS = readFileSync(join(HERE, "..", "styles", "storefront.css"), "utf8");

/** Resolved per-range stylesheets (var() substituted), for asserting that
 *  a rule exists inside ONE media query and not merely somewhere in the
 *  file. */
const MEDIA = loadStyles().media;
const mediaCss = (params) =>
  MEDIA.filter((entry) => entry.params === params)
    .map((entry) => entry.css)
    .join("\n")
    .replace(/\s+/g, " ");

const originalAdapter = apiClient.defaults.adapter;
const originalMatchMedia = window.matchMedia;

/** PR 20 gates the fold to phones, so the viewport is part of the harness:
 *  `phone` makes `(max-width: 767px)` match, everything else does not. */
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

/**
 * Let the post-toggle delta lock (350ms) expire. The unlock pass re-bases
 * lastY to the live scrollY and resets both travel counters, then schedules
 * one measurement frame -- awaited here so React state settles inside act().
 */
async function waitOutLock() {
  await act(async () => {
    // 350ms lock + a comfortable margin for timer/rAF scheduling.
    await new Promise((resolve) => setTimeout(resolve, 420));
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

function siteHeaderHeight() {
  return document.documentElement.style.getPropertyValue("--site-header-height");
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
  // The fold/measurement behaviours under test are the phone ones; the
  // desktop cases opt out explicitly with setPhoneViewport(false).
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
  MockResizeObserver.instances = [];
  window.ResizeObserver = MockResizeObserver;
});

afterEach(() => {
  cleanup();
  apiClient.defaults.adapter = originalAdapter;
  window.matchMedia = originalMatchMedia;
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

    await scrollTo(41);
    expect(header.className).toContain("site-header--compact");
    expect(header.className).not.toContain("site-header--collapsed");

    // The compact toggle locked deltas for 350ms; let a real gesture resume.
    await waitOutLock();

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
    await waitOutLock();
    await scrollTo(276);
    expect(header.className).not.toContain("site-header--collapsed");

    // ...and a second trip down folds it again.
    await waitOutLock();
    await scrollTo(300);
    expect(header.className).toContain("site-header--collapsed");

    // Reaching the top (<= 10px) always restores it, whatever the travel
    // (and even inside the lock window: the top is not a gesture).
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

  it("holds the folded row through a scroll-anchoring correction (the 375x812 loop)", async () => {
    renderHeader();
    const header = document.querySelector(".site-header");

    await scrollTo(480);
    expect(header.className).toContain("site-header--collapsed");

    // What the browser did on a real phone: shrink the header, scroll
    // anchoring corrected scrollY upward, this handler read the correction
    // as an upward swipe and expanded -- then the cycle repeated ~every
    // 40ms. Both corrections arrive inside the 350ms lock and are ignored.
    await scrollTo(457);
    expect(header.className).toContain("site-header--collapsed");

    await scrollTo(484);
    expect(header.className).toContain("site-header--collapsed");
  });

  it("accepts a real upward swipe again once the delta lock expires", async () => {
    renderHeader();
    const header = document.querySelector(".site-header");

    await scrollTo(480);
    expect(header.className).toContain("site-header--collapsed");

    // 30px up, but inside the lock window: still a correction, not a swipe.
    await scrollTo(450);
    expect(header.className).toContain("site-header--collapsed");

    // After the window the position is re-based, so the next 30px are read
    // as real travel and restore the full header.
    await waitOutLock();
    await scrollTo(420);
    expect(header.className).not.toContain("site-header--collapsed");
  });

  it("uses hysteresis for the compact state on every viewport", async () => {
    renderHeader();
    const header = document.querySelector(".site-header");
    await act(async () => {
      await nextFrame();
    });

    // Below the upper threshold nothing happens...
    await scrollTo(30);
    expect(header.className).not.toContain("site-header--compact");

    // ...past 40px it turns on...
    await scrollTo(41);
    expect(header.className).toContain("site-header--compact");

    // ...and it stays on well below that, down to the 8px release line.
    await scrollTo(20);
    expect(header.className).toContain("site-header--compact");

    await scrollTo(5);
    expect(header.className).not.toContain("site-header--compact");
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

  it("never folds beyond the phone boundary (PR 20 gating)", async () => {
    // The collapsed class used to be set on desktop too: harmless (its
    // styles are phone-only) but the state lied. On a wide viewport the
    // pill is the ONLY scrolled state, however far the shopper goes.
    setPhoneViewport(false);
    renderHeader();
    const header = document.querySelector(".site-header");

    await scrollTo(480);
    expect(header.className).toContain("site-header--compact");
    expect(header.className).not.toContain("site-header--collapsed");

    await waitOutLock();
    await scrollTo(600);
    expect(header.className).not.toContain("site-header--collapsed");
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

    // Compact but still expanded (scrollY > 40): the box is shorter.
    stubInnerHeight({ box: 58, content: 58 });
    await scrollTo(41);
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

  it("FLIP-pins the fold and releases the pin when the height settles", async () => {
    // PR 20: the expanded inner is `height: auto`, which cannot
    // transition -- so the fold pins the current height inline, lets
    // the class take over, and the pin is ALWAYS gone at rest. A stuck
    // pixel height is the bug this replaces.
    renderHeader();
    const header = document.querySelector(".site-header");
    const inner = document.querySelector(".site-header__inner");
    const heightSettled = () => {
      const event = new Event("transitionend");
      Object.defineProperty(event, "propertyName", { value: "height" });
      inner.dispatchEvent(event);
    };

    stubInnerHeight({ box: 124, content: 124 });
    await waitFor(() => expect(naturalHeight()).toBe("124px"));
    expect(inner.style.height).toBe("");

    // Fold: the pin is released to the collapsed class's row height
    // (inline height already gone; overflow stays pinned mid-flight).
    await scrollTo(220);
    expect(header.className).toContain("site-header--collapsed");
    expect(inner.style.height).toBe("");
    heightSettled();
    expect(inner.style.overflow).toBe("");

    // Expand: the pin targets the measured natural height...
    stubInnerHeight({ box: 56, content: 56 });
    await scrollTo(0);
    expect(header.className).not.toContain("site-header--collapsed");
    expect(inner.style.height).toBe("124px");

    // ...and is cleared back to auto when the transition settles.
    heightSettled();
    expect(inner.style.height).toBe("");
    expect(inner.style.overflow).toBe("");
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

  it("publishes --site-header-height from the EXPANDED phone header, folded or not", async () => {
    // PR 20: on phones the published offset is the expanded (spacer)
    // height. Live it followed the folded pill -- and on /checkout it
    // was EMPTY entirely, so anchor scroll-margins fell back to 92px.
    renderHeader();
    stubInnerHeight({ box: 124, content: 124 });
    await waitFor(() => expect(siteHeaderHeight()).toBe("124px"));
    expect(naturalHeight()).toBe("124px");

    // Folded to the pill the box is 56px, but sticky siblings hang off
    // the spacer behind the fixed header -- the offset must not follow.
    stubInnerHeight({ box: 56, content: 56 });
    await scrollTo(220);
    expect(document.querySelector(".site-header").className).toContain("site-header--collapsed");
    const observer = MockResizeObserver.instances.at(-1);
    await act(async () => {
      observer.trigger();
      await nextFrame();
    });
    expect(siteHeaderHeight()).toBe("124px");
  });

  it("publishes --site-header-height from the desktop OUTER box, pill or not", async () => {
    setPhoneViewport(false);
    renderHeader();
    const header = document.querySelector(".site-header");
    Object.defineProperty(header, "offsetHeight", { configurable: true, get: () => 76 });
    await waitFor(() => expect(siteHeaderHeight()).toBe("76px"));

    // The pill morphs INSIDE the outer box; the published offset is the
    // constant outer height in both states.
    await scrollTo(220);
    expect(header.className).toContain("site-header--compact");
    expect(siteHeaderHeight()).toBe("76px");
  });
});

describe("header spacer and pill state (PR 19)", () => {
  it("renders a sibling spacer that reserves the expanded natural height", async () => {
    renderHeader();
    const header = document.querySelector(".site-header");
    const spacer = document.querySelector(".site-header-spacer");
    expect(spacer).toBeTruthy();
    expect(spacer.getAttribute("aria-hidden")).toBe("true");
    expect(spacer.parentElement).toBe(header.parentElement);
    expect(header.nextElementSibling).toBe(spacer);

    stubInnerHeight({ box: 124, content: 124 });
    await waitFor(() => expect(naturalHeight()).toBe("124px"));
  });

  it("applies the pill as a class on the header, never as inline styles", async () => {
    renderHeader();
    const header = document.querySelector(".site-header");
    await scrollTo(120);
    expect(header.className).toContain("site-header--compact");
    expect(header.className).toContain("site-header--collapsed");
    // Pill geometry lives in the stylesheet only -- the document element
    // carries the measured height variables, the header carries classes.
    expect(header.getAttribute("style")).toBeNull();
  });
});

describe("header layout contract", () => {
  it("keeps a constant-height outer box on desktop and never transitions it", () => {
    // The sticky header's own height is the layout height: fixed at the
    // token, independent of compact/collapsed.
    expect(CSS).toMatch(/\.site-header \{\s*position: sticky; top: 0; z-index: 60;\s*isolation: isolate;\s*height: var\(--header-height\);/);
    // The morph is inner-only, and the outer height is not animated.
    const headerRule = [...CSS.matchAll(/\.site-header \{[^}]*\}/g)]
      .map((match) => match[0])
      .find((rule) => rule.includes("height: var(--header-height);"));
    expect(headerRule).toBeTruthy();
    expect(headerRule).not.toContain("transition");
    expect(CSS).toMatch(/\.site-header__inner \{[\s\S]*?transition:\s*[\s\S]*?width \.3s ease-out/);
  });

  it("renders the phone spacer with the natural height and fixed header", () => {
    expect(CSS).toMatch(/\.site-header-spacer \{ display: none; \}/);
    expect(CSS).toMatch(/@media \(max-width: 767px\) \{[\s\S]*?\.site-header \{\s*position: fixed;\s*top: 0;\s*inset-inline: 0;[\s\S]*?\.site-header-spacer \{\s*display: block;[\s\S]*?height: var\(--header-natural-height, 124px\);/);
    // The spacer is not allowed to animate with the collapse.
    expect(CSS).toMatch(/\.site-header-spacer \{[^}]*transition: none/);
  });

  it("morphs the desktop bar into the floating pill", () => {
    const compact = CSS.replace(/\s+/g, " ").match(/\.site-header--compact \.site-header__inner \{[^}]*\}/)[0];
    // PR 20: 80% wrapped every label at 1024px into an 87px pill.
    expect(compact).toContain("width: calc(100% - 32px);");
    expect(compact).toContain("max-width: 1160px;");
    // The exact compact height is what keeps the pill inside the 76px
    // outer box (12px float margin + 60px = 72px).
    expect(compact).toContain("height: var(--header-height-compact);");
    expect(compact).toContain("margin-top: 12px;");
    expect(compact).toContain("border-radius: 16px;");
    expect(compact).toContain("border-color: rgba(206,180,100,.35);");
    expect(compact).toContain("box-shadow: 0 8px 24px rgba(20,26,10,.25);");
    expect(compact).toContain("background-color: rgba(47,58,24,.88);");
    // The blur lives on the descendant-free pseudo layer (never on the bar
    // itself, which would capture the mega-menu's fixed overlay).
    expect(CSS.replace(/\s+/g, " ")).toMatch(
      /\.site-header--compact \.site-header__inner::before \{ -webkit-backdrop-filter: blur\(12px\); backdrop-filter: blur\(12px\); \}/
    );
    // The transition list animates the pill's geometry, not the outer box.
    const inner = [...CSS.replace(/\s+/g, " ").matchAll(/\.site-header__inner \{[^}]*\}/g)]
      .map((match) => match[0])
      .find((rule) => rule.includes("transition:"));
    expect(inner).toBeTruthy();
    for (const prop of ["width .3s ease-out", "max-width .3s ease-out", "margin .3s ease-out", "padding .3s ease-out", "border-radius .3s ease-out", "background-color .3s ease-out", "box-shadow .3s ease-out"]) {
      expect(inner, `transition must include ${prop}`).toContain(prop);
    }
  });

  it("folds the phone row into the same pill and restores the search field", () => {
    // PR 20: expanded = height:auto, NEVER a pinned pixel/var height --
    // a locked box can only re-measure itself (live: 190px for 246px of
    // content, search row spilling over the page).
    expect(CSS).toMatch(/\.site-header__inner \{\s*flex-wrap: wrap;\s*row-gap: 10px;\s*\/\*[\s\S]*?\*\/\s*height: auto;/);
    expect(CSS).not.toMatch(/height: var\(--header-natural-height, auto\)/);
    const collapsed = CSS.replace(/\s+/g, " ").match(/\.site-header--collapsed \.site-header__inner \{[^}]*\}/)[0];
    expect(collapsed).toContain("height: var(--header-height-row);");
    expect(collapsed).toContain("margin: 8px;");
    expect(collapsed).toContain("border-radius: 14px;");
    expect(collapsed).toContain("border-color: rgba(206,180,100,.35);");
    expect(collapsed).toContain("background-color: rgba(47,58,24,.88);");
    expect(CSS.replace(/\s+/g, " ")).toMatch(
      /\.site-header--collapsed \.site-header__inner::before \{ -webkit-backdrop-filter: blur\(12px\); backdrop-filter: blur\(12px\); \}/
    );
    expect(CSS).toMatch(/\.site-header--collapsed \.site-header__search-toggle \{ display: inline-grid; \}/);
  });

  it("keeps the searching pill's field inside the pill as a second row", () => {
    // PR 20: the revealed field used to stay in the nowrap pill row and
    // stick ~147px out of it (x=-139..199 at 375px). The searching pill
    // wraps instead: icons on row 1, the field on row 2 inside the
    // padding, shrinkable all the way down (min-width: 0).
    const flat = CSS.replace(/\s+/g, " ");
    const inner = flat.match(/\.site-header--collapsed\.site-header--searching \.site-header__inner \{[^}]*\}/)[0];
    expect(inner).toContain("height: auto;");
    expect(inner).toContain("flex-wrap: wrap;");
    expect(inner).toContain("overflow: visible;");
    const search = flat.match(/\.site-header--collapsed\.site-header--searching \.site-header__search \{[^}]*\}/)[0];
    expect(search).toContain("display: flex;");
    expect(search).toContain("flex: 1 1 100%;");
    expect(search).toContain("max-width: 100%;");
    expect(search).toContain("min-width: 0;");
    expect(flat).toContain(
      ".site-header--collapsed.site-header--searching .site-header__search input { flex: 1 1 auto; min-width: 0; }"
    );
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

  it("keeps the phone header fixed with a spacer owning its flow height", () => {
    // The only `position: fixed` header is inside the phone breakpoint, and
    // it is paired with a static-height spacer -- the document height never
    // depends on the collapsed state.
    expect(CSS).toMatch(/@media \(max-width: 767px\) \{[\s\S]*?\.site-header \{\s*position: fixed;/);
    expect(CSS.replace(/\s+/g, " ")).toContain("height: var(--header-natural-height, 124px);");
  });

  it("gives the desktop bar an exact border-box height (79px-inside-76px fix)", () => {
    // PR 20: at rest the inner painted 79px inside the 76px outer box
    // (min-height + the transparent border). The bar's own box is now
    // exactly var(--header-height), border included.
    const inner = [...CSS.replace(/\s+/g, " ").matchAll(/\.site-header__inner \{[^}]*\}/g)]
      .map((match) => match[0])
      .find((rule) => rule.includes("background-color: var(--brand-green-dark);"));
    expect(inner).toBeTruthy();
    expect(inner).toContain("box-sizing: border-box;");
    expect(inner).toContain("height: var(--header-height);");
  });

  it("makes the phone header exactly two rows: no mega trigger, search on row 2", () => {
    const phone = mediaCss("(max-width: 767px)");
    // The «دسته‌بندی کالاها» trigger leaves the phone header entirely
    // (the burger drawer opens the same sheet).
    expect(phone).toContain(".site-header__mega-trigger { display: none; }");
    // Row 2 is the full-width search.
    const search = phone.match(/\.site-header__search \{[^}]*\}/g) || [];
    expect(search.some((rule) => rule.includes("order: 3") && rule.includes("100%"))).toBe(true);
    // And the expanded inner wraps (so there IS a second row) at auto.
    expect(phone).toContain("height: auto;");
  });

  it("gives tablets (768-1099px) the compact one-row chrome", () => {
    const tablet = mediaCss("(min-width: 768px) and (max-width: 1099px)");
    // Live at 820px: 29px search, wrapping labels, 87px pill. Now:
    expect(tablet).toContain(".site-header__nav { display: none; }");
    expect(tablet).toContain(".site-header__burger { display: block; }");
    // Mega trigger: icon + SHORT label (the full label swaps out).
    expect(tablet).toContain(".site-header__mega-label { display: none; }");
    expect(tablet).toContain(".site-header__mega-label--short { display: inline; }");
    // The search flexes with a real floor.
    expect(tablet).toContain("min-width: 220px;");
    // One row, always (the ≤1199px tightening never re-wraps it).
    expect(tablet).toContain(".site-header__inner { flex-wrap: nowrap; }");
    // Account is icon-only at and below this range.
    const iconOnly = mediaCss("(max-width: 1099px)");
    expect(iconOnly).toContain(".user-menu__trigger-label");
    expect(iconOnly).toContain(".site-header__login-label { display: none; }");
    // And the labels that DO show (>=1100px) can never wrap.
    const flat = CSS.replace(/\s+/g, " ");
    expect(flat).toContain(".site-header__mega-btn {");
    expect(flat.match(/\.site-header__mega-btn \{[^}]*white-space: nowrap;/)).toBeTruthy();
    expect(flat.match(/\.user-menu__trigger \{[^}]*white-space: nowrap;/)).toBeTruthy();
    expect(flat.match(/\.site-header__nav a \{[^}]*white-space: nowrap;/)).toBeTruthy();
  });

  it("detaches the mega dropdown from the pill: centred, capped, nothing sticks out", () => {
    // PR 20: in pill mode the panel was wider than the pill and hung off
    // the left edge of the viewport at 1024px (inner x=-55).
    const flat = CSS.replace(/\s+/g, " ");
    const menu = flat.match(/\.mega-menu \{[^}]*\}/)[0];
    expect(menu).toContain("width: min(1160px, calc(100vw - 32px));");
    expect(menu).toContain("left: 50%;");
    expect(menu).toContain("transform: translateX(-50%);");
    expect(menu).toContain("top: 100%;");
    const inner = flat.match(/\.mega-menu__inner \{[^}]*\}/)[0];
    expect(inner).toContain("max-width: 100%;");
    expect(inner).not.toContain("94vw");
    // The dim starts at the pill's bottom when compact.
    expect(flat).toContain(
      ".site-header--compact .mega-menu__overlay { top: calc(12px + var(--header-height-compact)); }"
    );
  });
});

describe("phone header markup (PR 20 two rows)", () => {
  it("orders row 1 as burger, brand, actions -- with the search wrapping to row 2", () => {
    renderHeader();
    const inner = document.querySelector(".site-header__inner");
    const burger = inner.querySelector(".site-header__burger");
    const brand = inner.querySelector(".site-header__brand");
    const search = inner.querySelector(".site-header__search");
    const actions = inner.querySelector(".site-header__actions");
    // DOM order puts the account + cart (actions) after the brand, and the
    // search carries the order-3/full-basis phone treatment (asserted in
    // the CSS contract above), so visually it wraps under them.
    expect(burger.compareDocumentPosition(brand) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(brand.compareDocumentPosition(actions) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(search).toBeTruthy();
    // The cart (with its badge slot) lives in the actions cluster.
    expect(actions.querySelector(".cart-link")).toBeTruthy();
  });

  it("keeps an accessible name on the icon-only account controls", () => {
    renderHeader();
    // Logged out: the login link is icon-only at <=1099px (CSS), so it
    // must not lose its name when the label hides.
    const login = document.querySelector(".site-header__login");
    expect(login).toBeTruthy();
    expect(login.getAttribute("aria-label")).toBe("ورود | ثبت‌نام");
    expect(login.querySelector(".site-header__login-label").textContent).toBe("ورود | ثبت‌نام");
    expect(login.querySelector("svg")).toBeTruthy();
  });

  it("labels the account button «حساب کاربری» and pairs the icon with the name", () => {
    const realFetchMe = useAuthStore.getState().fetchMe;
    useAuthStore.setState({
      user: { first_name: "سارا" },
      isAuthenticated: true,
      isLoading: false,
      fetchMe: async () => ({ success: true }),
    });
    try {
      renderHeader();
      const trigger = document.querySelector(".user-menu__trigger");
      expect(trigger).toBeTruthy();
      expect(trigger.getAttribute("aria-label")).toBe("حساب کاربری");
      expect(trigger.querySelector("svg")).toBeTruthy();
      expect(trigger.querySelector(".user-menu__trigger-label").textContent).toBe("سارا");
    } finally {
      useAuthStore.setState({ fetchMe: realFetchMe });
    }
  });
});
