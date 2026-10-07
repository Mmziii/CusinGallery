/**
 * Part S5 follow-up 4, item 2: invisible text in the cart.
 *
 * (a) The mini-cart product name was painted in the HEADER's ivory text color
 *     (`.site-header` sets `color: var(--brand-ivory)`) on the white drawer
 *     panel: measured 1.07:1 -- effectively invisible, exactly as the owner
 *     reported. Every text cell of the drawer now declares its own color.
 *
 * (b) The cart page title: the RESOLVED CASCADE gives it rgb(47, 58, 24) on
 *     rgb(250, 247, 240) = 11.28:1 -- no color rule washes it out and no
 *     ancestor paints it light, so the "light text" hypothesis is disproved by
 *     measurement. What the screenshot matches instead is geometry: from
 *     scrollY > 24 the header turns compact (`backdrop-filter: blur(12px)`,
 *     85% opaque) and, at a scroll offset of roughly its own height, covers the
 *     48px-tall title while the guest note lands right below the bar -- a
 *     layout effect jsdom cannot see (no layout engine in this environment, and
 *     no browser is installable here). What this file does pin is the
 *     structural half of the guarantee, which is what a test can honestly
 *     assert: the title owns a `color` declaration of its own (`.page-title`,
 *     not inheritance from whatever container it lands in) and is measured at
 *     >= 4.5:1 against its real backdrop.
 *
 * (c) How the audit works (mechanism, in src/test/cssCascade.js): the three
 *     real stylesheets are parsed with postcss, every `var(--token)` is
 *     resolved from `:root`, the result is injected into the mounted jsdom
 *     document, and the winning color/background of every text-owning element
 *     are read back through `getComputedStyle` (so matching, order,
 *     specificity and `!important` are decided by the DOM engine on the real
 *     tree). Backgrounds are composited through translucent ancestors and
 *     compared with the WCAG 2.1 ratio (4.5:1, 3:1 for large text).
 *     Limits, stated openly: flat colors only (no gradients, images, opacity
 *     or backdrop-filter over text), `@media` blocks are collected separately
 *     instead of evaluated (jsdom has no viewport -- one test below asserts
 *     the audited surfaces take no color from them), and there is no geometry,
 *     so overlapping/scrolled content cannot be modelled. Visual verification
 *     was impossible in this environment: no browser or headless engine is
 *     installable (no chromium/firefox, no Playwright, no GTK/NSS/GBM system
 *     libraries and no apt).
 */
import postcss from "postcss";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import App from "../App";
import Header from "../components/Header";
import apiClient from "../services/apiClient";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import {
  auditContrast,
  computedBackdrop,
  computedForeground,
  contrastRatio,
  fmt,
  installStyles,
  isLargeText,
  loadStyles,
  winningDeclaration,
} from "../test/cssCascade";

const priceInfo = (price, compareAt = null) => ({
  price,
  compare_at_price: compareAt,
  discount_percentage: compareAt ? 30 : 0,
  is_on_sale: Boolean(compareAt),
  discount_amount: compareAt ? compareAt - price : 0,
});

const PRODUCTS = {
  1: { id: 1, name: "قابلمه گرانیتی", slug: "pan-1", primary_image: null, price_info: priceInfo(50000) },
  2: { id: 2, name: "سرویس بلور", slug: "glass-2", primary_image: null, price_info: priceInfo(60000, 90000) },
  3: { id: 3, name: "کتری استیل", slug: "kettle-3", primary_image: null, price_info: priceInfo(30000) },
};

const GUEST_LINES = [
  { product_id: 1, variant_id: null, quantity: 2 },
  { product_id: 2, variant_id: null, quantity: 1 },
  { product_id: 3, variant_id: 33, quantity: 3 },
];

const KETTLE_VARIANT = {
  id: 33,
  sku: "KETTLE-BLK",
  price_info: priceInfo(45000),
  stock_status: "in_stock",
  is_in_stock: true,
  is_active: true,
  image: null,
  attribute_values: [{ id: 7, attribute: "رنگ", attribute_slug: "color", value: "مشکی" }],
};

const SERVER_CART = {
  items: [
    {
      id: 11, quantity: 2, is_available: true, unavailable_reason: null,
      product: { id: 1, name: "قابلمه گرانیتی", slug: "pan-1", primary_image: null },
      variant: null, price_info: priceInfo(50000), line_total: 100000,
    },
  ],
  item_count: 2, subtotal: 100000, total: 100000, shipping_cost_preview: 45000,
};

const ACCOUNT = { id: 1, phone: "09120000000", first_name: "آزمون" };
const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    const method = (config.method || "get").toLowerCase();
    const ok = (data) => ({ data, status: 200, statusText: "OK", headers: {}, config });
    if (url === "/products/") {
      const ids = String((config.params || {}).ids || "").split(",").filter(Boolean).map(Number);
      return ok({ count: ids.length, next: null, previous: null, results: ids.map((id) => PRODUCTS[id]).filter(Boolean) });
    }
    if (method === "get" && /^\/products\/[^/]+\/$/.test(url)) {
      const slug = url.replace("/products/", "").replace(/\/$/, "");
      const product = Object.values(PRODUCTS).find((item) => item.slug === slug);
      return ok({ ...(product || {}), variants: slug === "kettle-3" ? [KETTLE_VARIANT] : [] });
    }
    if (/categories\/tree/.test(url)) return ok([]);
    if (/^\/categories\//.test(url)) return ok({ count: 0, results: [] });
    if (/^\/brands\//.test(url)) return ok({ count: 0, results: [] });
    if (/products\/facets\//.test(url)) return ok({ results: [] });
    if (/^\/banners\//.test(url)) return ok({ results: [] });
    if (url === "/site/settings/") return ok({});
    if (url === "/accounts/me/") return ok(useAuthStore.getState().isAuthenticated ? ACCOUNT : { user: null });
    if (url === "/cart/") return ok(SERVER_CART);
    if (url === "/orders/shipping-methods/") {
      return ok({
        default: "standard", gift_wrap_fee: 0,
        methods: [{ id: "standard", label: "ارسال عادی", cost: 45000, free_threshold: null, min_days: 3, max_days: 5, requires_address: true }],
      });
    }
    if (url === "/accounts/addresses/") return ok([]);
    return originalAdapter(config);
  };
});
afterAll(() => { apiClient.defaults.adapter = originalAdapter; });

beforeEach(() => {
  localStorage.clear();
  useCartStore.setState({
    cart: null, guestLines: [], guestProducts: {}, guestVariants: {},
    guestHydration: "idle", guestHydrationError: null, isLoading: false, error: null,
  });
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
});
afterEach(() => cleanup());

/** Renders + injects the real stylesheets (the audit reads them back through
 *  getComputedStyle, so nothing else is needed). */
function renderWithStyles(node, route = "/") {
  const view = render(<MemoryRouter initialEntries={[route]}>{node}</MemoryRouter>);
  installStyles(document);
  return view;
}

function failuresOf(rows) {
  return rows.filter((row) => !row.pass);
}

function expectNoFailures(rows, label) {
  const lines = failuresOf(rows).map(
    (row) => `${fmt(row.fg)} on ${fmt(row.bg)} = ${row.ratio.toFixed(2)} (needs ${row.min}) <${row.tag}> "${row.text}"`
  );
  expect(lines, `${label}: contrast failures\n${lines.join("\n")}`).toEqual([]);
  expect(rows.length, `${label}: nothing was measured`).toBeGreaterThan(5);
}

/** Contrast of one element, measured the way the audit measures it. */
function measure(element) {
  const foreground = computedForeground(window, element);
  const backdrop = computedBackdrop(window, element);
  return {
    foreground,
    backdrop,
    ratio: contrastRatio(foreground, backdrop),
    large: isLargeText(window, element),
  };
}

describe("computed contrast on the cart surfaces (item 2)", () => {
  it("keeps the mini-cart drawer legible (the ivory-on-white bug)", async () => {
    useCartStore.setState({ guestLines: GUEST_LINES, guestHydration: "ready", guestProducts: {} });
    const view = renderWithStyles(<Header />);
    const cartLink = await waitFor(() => {
      const node = view.container.querySelector(".cart-link");
      expect(node).toBeTruthy();
      return node;
    });
    fireEvent.click(cartLink);

    const drawer = await waitFor(() => {
      const node = document.querySelector(".minicart");
      expect(node).toBeTruthy();
      return node;
    });
    await waitFor(() => expect(drawer.querySelectorAll(".minicart__items li").length).toBe(3));

    // The old cascade painted the product name in the header's ivory
    // (rgb(250,247,240)) on the white panel -- 1.07:1 -- because the drawer
    // was a child of <header>. Measured now, every text cell of the drawer:
    for (const cls of ["minicart__panel", "minicart__name", "minicart__qty", "minicart__price"]) {
      const node = drawer.querySelector(`.${cls}`);
      expect(node, cls).toBeTruthy();
      const { foreground, backdrop, ratio } = measure(node);
      expect(ratio, `${cls}: ${fmt(foreground)} on ${fmt(backdrop)}`).toBeGreaterThanOrEqual(4.5);
    }
    // The panel itself must state its text color, not inherit the header's.
    expect(winningDeclaration(drawer.querySelector(".minicart__panel"), "color")?.value).toBeTruthy();
    expect(winningDeclaration(drawer.querySelector(".minicart__panel"), "color")?.value).not.toMatch(
      /ivory|inherit/
    );
    expectNoFailures(auditContrast(window, drawer, {}), "mini-cart");
  });

  it("keeps every text pair on the guest cart page at 4.5:1 or better", async () => {
    useCartStore.setState({ guestLines: GUEST_LINES, guestHydration: "idle" });
    localStorage.setItem("cusin_recently_viewed", JSON.stringify([1]));
    const view = renderWithStyles(<App />, "/cart/");
    await screen.findByText("قابلمه گرانیتی");
    await screen.findByText("اخیراً دیده‌اید");

    expectNoFailures(auditContrast(window, view.container, {}), "guest cart page");
  });

  it("keeps the skeleton state legible too (product data still in flight)", async () => {
    const hanging = apiClient.defaults.adapter;
    let view;
    try {
      apiClient.defaults.adapter = async (config) =>
        (config.url || "") === "/products/" ? new Promise(() => {}) : hanging(config);
      useCartStore.setState({ guestLines: GUEST_LINES, guestHydration: "idle" });
      view = renderWithStyles(<App />, "/cart/");
      await screen.findByText("در حال دریافت اطلاعات کالاها…");
      expectNoFailures(auditContrast(window, view.container, {}), "cart skeleton");
    } finally {
      apiClient.defaults.adapter = hanging;
    }
  });

  it("keeps the authenticated cart page legible", async () => {
    useAuthStore.setState({ user: ACCOUNT, isAuthenticated: true, isLoading: false });
    const view = renderWithStyles(<App />, "/cart/");
    await screen.findByText("قابلمه گرانیتی");

    expectNoFailures(auditContrast(window, view.container, {}), "authenticated cart page");
  });

  it("keeps the checkout page legible, including the summary", async () => {
    useAuthStore.setState({ user: ACCOUNT, isAuthenticated: true, isLoading: false });
    const view = renderWithStyles(<App />, "/checkout/");
    await screen.findByRole("heading", { name: "ثبت سفارش" });
    const summary = await waitFor(() => {
      const node = view.container.querySelector(".checkout__summary");
      expect(node).toBeTruthy();
      return node;
    });
    expect(summary.textContent).toContain("جمع کالاها");

    expectNoFailures(auditContrast(window, view.container, {}), "checkout page");
  });

  it("keeps the recently-viewed strip legible and it lives on the cart page", async () => {
    useCartStore.setState({ guestLines: GUEST_LINES, guestHydration: "idle" });
    localStorage.setItem("cusin_recently_viewed", JSON.stringify([1, 2]));
    const view = renderWithStyles(<App />, "/cart/");
    await screen.findByText("اخیراً دیده‌اید");

    const strip = view.container.querySelector(".recently-viewed");
    expect(strip).toBeTruthy();
    expectNoFailures(auditContrast(window, strip, {}), "recently-viewed strip");
  });

  it("gives the cart title its own color declaration instead of inheriting", async () => {
    useCartStore.setState({ guestLines: GUEST_LINES, guestHydration: "idle" });
    const view = renderWithStyles(<App />, "/cart/");
    await screen.findByText("قابلمه گرانیتی");

    const title = view.container.querySelector("h1");
    expect(title.textContent).toBe("سبد خرید");
    // It must not sit inside the header, whose ivory text color is what made
    // the mini-cart unreadable, and its color must come from its own rule.
    expect(title.closest(".site-header")).toBeNull();
    const declared = winningDeclaration(title, "color");
    expect(declared?.selector, "the cart title needs its own color rule").toContain(".page-title");
    expect(declared.value).toMatch(/brand-green-dark|#2F3A18/i);

    const { foreground, backdrop, ratio } = measure(title);
    expect(ratio, `cart title: ${fmt(foreground)} on ${fmt(backdrop)}`).toBeGreaterThanOrEqual(4.5);
  });

  it("would catch a light-on-light regression (the check really checks)", async () => {
    useCartStore.setState({ guestLines: GUEST_LINES, guestHydration: "idle" });
    const view = renderWithStyles(<App />, "/cart/");
    await screen.findByText("قابلمه گرانیتی");

    // Recreate the bug shape as a synthetic probe with inline styles (so the
    // fix under test cannot rewrite it): ivory text on the white panel.
    const panel = document.createElement("div");
    panel.setAttribute("style", "background-color: rgb(255, 255, 255)");
    const probe = document.createElement("span");
    probe.setAttribute("style", "color: rgb(250, 247, 240)");
    probe.textContent = "پروب کنتراست";
    panel.appendChild(probe);
    view.container.appendChild(panel);

    const { foreground, backdrop, ratio } = measure(probe);
    expect(fmt(foreground)).toBe("rgb(250, 247, 240)");
    expect(fmt(backdrop)).toBe("rgb(255, 255, 255)");
    expect(ratio).toBeLessThan(1.1);

    const rows = auditContrast(window, view.container, {});
    const flagged = failuresOf(rows).filter((row) => row.el === probe);
    expect(flagged.length).toBe(1);
    expect(flagged[0].text).toBe("پروب کنتراست");
  });

  it("documents the @media limit: the audited surfaces take no color from media queries", () => {
    const { media } = loadStyles();
    expect(media.length).toBeGreaterThan(0);
    // No @media rule may color a text element of the audited surfaces: jsdom
    // cannot evaluate the condition, so such a rule would be a blind spot.
    const audited = /\.(minicart|cart-page|cart-item|checkout|checkout-done|recently-viewed|page-title)/;
    const offenders = [];
    for (const block of media) {
      postcss.parse(block.css).walkRules((rule) => {
        if (!audited.test(rule.selector)) return;
        rule.walkDecls(/^(color|background(-color)?)$/, (decl) => {
          offenders.push(`${block.params}: ${rule.selector} { ${decl.prop}: ${decl.value} }`);
        });
      });
    }
    expect(offenders, offenders.join("\n")).toEqual([]);
  });
});
