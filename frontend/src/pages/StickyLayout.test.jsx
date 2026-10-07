/**
 * Part S5 follow-up 4, item 4: "خلاصه سفارش روی «اخیراً دیده‌اید» می‌افتد"
 * (the sticky cart summary slid over the recently-viewed section).
 *
 * Root cause: on the GUEST cart page the summary was a direct child of
 * `.cart-page` (a plain block container), and `.cart-page` also contains the
 * «اخیراً دیده‌اید» strip. A sticky box may travel down to the bottom of its
 * containing block, so as soon as the page scrolled the sticky summary
 * detached, followed the viewport and -- being positioned -- painted ON TOP
 * of the (static) recently-viewed cards. The page had no dedicated wrapper
 * bounding the sticky travel, and below the desktop breakpoint the same
 * summary was still sticky on an already stacked layout.
 *
 * This file pins the structure the fix requires, in the browser's own terms
 * (jsdom has no layout, so "would it overlap?" is expressed as "what box can
 * the sticky element travel within?" -- the nearest box that contains it and
 * also contains `position: sticky` semantics: the parent when that parent is
 * a grid/flex container (a grid item's containing block is its grid area),
 * otherwise the nearest block container):
 *   - the sticky summary's travel box must NOT contain the sections that
 *     come after it (recently-viewed and anything below);
 *   - the summary lives in a dedicated `.cart-page__body` wrapper that
 *     contains only the items+summary grid and ends before those sections;
 *   - that wrapper is a stacking context (position: relative + z-index), so
 *     nothing inside the page can paint over the sticky header (z 60) or the
 *     drawers (115/116);
 *   - checkout/shop/account follow the same rule, and every sticky element
 *     is disabled below its desktop breakpoint (CSS source assertions).
 */
import fs from "node:fs";
import path from "node:path";

import postcss from "postcss";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import AccountLayout from "./account/AccountLayout";
import CartPage from "./CartPage";
import CheckoutPage from "./CheckoutPage";
import ShopPage from "./ShopPage";

const CSS_PATH = path.resolve(__dirname, "../styles/storefront.css");

/** Parsed view of the real stylesheet: every rule with its declarations and
 *  the @media it lives inside (postcss, so nested at-rules are handled
 *  correctly). Declarations are read from the AUTHORED source -- jsdom cannot
 *  evaluate media queries, so "is sticky off on mobile?" is a source
 *  assertion, exactly like the contrast audit's @media note. */
function parseCss() {
  const root = postcss.parse(fs.readFileSync(CSS_PATH, "utf8"));
  const rules = [];
  root.walkRules((rule) => {
    const declarations = {};
    rule.walkDecls((decl) => {
      declarations[decl.prop] = decl.value;
    });
    rules.push({
      selectors: rule.selector.split(",").map((value) => value.trim()),
      declarations,
      media: rule.parent.type === "atrule" && rule.parent.name === "media" ? rule.parent.params : null,
    });
  });
  return rules;
}

/** Effective declarations for `selector`: later rules win (browser order),
 *  optionally restricted to the rules inside one @media. */
function effectiveDeclarations(rules, selector, media = undefined) {
  const out = {};
  for (const rule of rules) {
    if (media !== undefined && rule.media !== media) continue;
    if (!rule.selectors.includes(selector)) continue;
    Object.assign(out, rule.declarations);
  }
  return out;
}

// ---------------------------------------------------------------- rendering

const priceInfo = (price) => ({
  price, compare_at_price: null, discount_percentage: 0, is_on_sale: false, discount_amount: 0,
});

const PRODUCT = {
  id: 1, name: "قابلمه گرانیتی", slug: "pan-1", primary_image: null, price_info: priceInfo(50000),
};

const SERVER_CART = {
  items: [
    {
      id: 11, quantity: 1, is_available: true, unavailable_reason: null,
      product: { id: 1, name: "قابلمه گرانیتی", slug: "pan-1", primary_image: null },
      variant: null, price_info: priceInfo(50000), line_total: 50000,
    },
  ],
  item_count: 1, subtotal: 50000, total: 50000, shipping_cost_preview: 45000,
};

const originalAdapter = apiClient.defaults.adapter;
beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    const ok = (data) => ({ data, status: 200, statusText: "OK", headers: {}, config });
    if (url === "/products/") {
      const ids = String((config.params || {}).ids || "");
      return ok(ids ? { count: 1, next: null, previous: null, results: [PRODUCT] }
        : { count: 1, next: null, previous: null, results: [PRODUCT] });
    }
    if (/categories\/tree/.test(url)) return ok([]);
    if (/^\/categories\//.test(url)) return ok({ count: 0, results: [] });
    if (/^\/brands\//.test(url)) return ok({ count: 0, results: [] });
    if (/products\/facets\//.test(url)) return ok({ results: [] });
    if (url === "/site/settings/") return ok({});
    if (url === "/accounts/me/") return ok({ user: null });
    if (url === "/cart/") return ok(SERVER_CART);
    if (url === "/orders/shipping-methods/") {
      return ok({ default: "standard", gift_wrap_fee: 0, methods: [
        { id: "standard", label: "ارسال عادی", cost: 45000, free_threshold: null, min_days: 3, max_days: 5, requires_address: true },
      ] });
    }
    if (url === "/accounts/addresses/") return ok([]);
    return originalAdapter(config);
  };
});
afterAll(() => { apiClient.defaults.adapter = originalAdapter; });

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("cusin_recently_viewed", JSON.stringify([1]));
  useCartStore.setState({
    cart: null, guestLines: [{ product_id: 1, variant_id: null, quantity: 1 }],
    guestProducts: {}, guestVariants: {}, guestHydration: "idle",
    guestHydrationError: null, isLoading: false, error: null,
  });
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
});
afterEach(() => cleanup());

/** The box a `position: sticky` element may travel within: its parent when
 *  that parent is a grid/flex container (the parent's box holds the grid
 *  area), otherwise the nearest block-container ancestor. */
function stickyTravelBox(element) {
  const parent = element.parentElement;
  if (!parent) return null;
  const display = window.getComputedStyle(parent).display;
  if (["grid", "inline-grid", "flex", "inline-flex"].includes(display)) return parent;
  let node = parent;
  while (node) {
    const nodeDisplay = window.getComputedStyle(node).display;
    if (["block", "flow-root", "list-item"].includes(nodeDisplay)) return node;
    node = node.parentElement;
  }
  return null;
}

function assertStickyTravelSafe(summary, forbiddenSelector, label) {
  const box = stickyTravelBox(summary);
  expect(box, `${label}: no travel box found for the sticky summary`).toBeTruthy();
  const forbidden = document.querySelector(forbiddenSelector);
  expect(forbidden, `${label}: ${forbiddenSelector} is not rendered`).toBeTruthy();
  // The sticky box can reach the bottom edge of its containing block; if the
  // next section is INSIDE that box, it paints over it while scrolling.
  expect(box.contains(forbidden), `${label}: sticky box contains ${forbiddenSelector}`).toBe(false);
  // ...and the wrapper itself must come BEFORE the next section.
  expect(box.compareDocumentPosition(forbidden) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
}

describe("sticky summary containment (item 4)", () => {
  it("guest cart: the sticky summary cannot travel over «اخیراً دیده‌اید»", async () => {
    const view = render(
      <MemoryRouter initialEntries={["/cart/"]}>
        <CartPage />
      </MemoryRouter>
    );
    await screen.findByText("قابلمه گرانیتی");
    await screen.findByText("اخیراً دیده‌اید");

    const summary = view.container.querySelector(".cart-page__summary");
    assertStickyTravelSafe(summary, ".recently-viewed", "guest cart");

    // The summary sits in a dedicated wrapper that holds the items+summary
    // grid -- and nothing else.
    const body = summary.closest(".cart-page__body");
    expect(body, "the cart page needs a dedicated .cart-page__body wrapper").toBeTruthy();
    expect(body.children.length).toBe(1);
    expect(body.firstElementChild.classList.contains("cart-page__grid")).toBe(true);
    expect(body.contains(document.querySelector(".recently-viewed"))).toBe(false);
    expect(body.contains(summary)).toBe(true);
  });

  it("authenticated cart: same wrapper, same guarantee", async () => {
    useAuthStore.setState({ user: { id: 1 }, isAuthenticated: true, isLoading: false });
    useCartStore.setState({ cart: null });
    const view = render(
      <MemoryRouter initialEntries={["/cart/"]}>
        <CartPage />
      </MemoryRouter>
    );
    await screen.findByText("قابلمه گرانیتی");

    const summary = view.container.querySelector(".cart-page__summary");
    assertStickyTravelSafe(summary, ".recently-viewed", "authenticated cart");
    const body = summary.closest(".cart-page__body");
    expect(body).toBeTruthy();
    expect(body.children.length).toBe(1);
  });

  it("checkout: the sticky summary sits in a wrapper that ends the page body", async () => {
    useAuthStore.setState({ user: { id: 1 }, isAuthenticated: true, isLoading: false });
    const view = render(
      <MemoryRouter initialEntries={["/checkout/"]}>
        <CheckoutPage />
      </MemoryRouter>
    );
    const summary = await screen.findByText("خلاصه سفارش");
    const aside = summary.closest(".checkout__summary");

    const body = aside.closest(".checkout__body");
    expect(body, "the checkout needs a dedicated .checkout__body wrapper").toBeTruthy();
    expect(body.children.length).toBe(1);
    expect(body.firstElementChild.classList.contains("checkout__grid")).toBe(true);
    // Nothing follows the grid inside the page: the sticky box ends with it.
    expect(body.parentElement.lastElementChild).toBe(body);
    expect(stickyTravelBox(aside)).toBe(view.container.querySelector(".checkout__grid"));
  });

  it("shop: the sticky sidebar's container is the last thing on the page", async () => {
    const view = render(
      <MemoryRouter initialEntries={["/shop/"]}>
        <ShopPage />
      </MemoryRouter>
    );
    const sidebar = await screen.findByRole("complementary", { name: /فیلتر/ }).catch(() => null);
    const aside = sidebar || view.container.querySelector(".shop__sidebar");
    expect(aside).toBeTruthy();
    const box = stickyTravelBox(aside);
    expect(box.classList.contains("shop")).toBe(true);
    // Nothing follows the sidebar's containing block inside the page.
    expect(box.parentElement.lastElementChild).toBe(box);
  });

  it("account: the sticky nav shares its containing block with the content column only", () => {
    const view = render(
      <MemoryRouter initialEntries={["/account/"]}>
        <Routes>
          <Route path="/account/" element={<AccountLayout />} />
        </Routes>
      </MemoryRouter>
    );
    const nav = view.container.querySelector(".account__nav");
    expect(nav).toBeTruthy();
    const box = stickyTravelBox(nav);
    expect(box.classList.contains("account")).toBe(true);
    // The nav's containing block holds exactly the two columns (nav +
    // content) -- there is no third section inside it.
    expect(box.children.length).toBe(2);
    expect(box.querySelector(".account__content")).toBeTruthy();
  });
});

describe("sticky CSS contract (item 4)", () => {
  it("keeps the list of sticky elements explicit -- a new one must be audited", () => {
    const rules = parseCss();
    const selectors = new Set();
    for (const rule of rules) {
      if (rule.declarations.position === "sticky") {
        for (const selector of rule.selectors) selectors.add(selector);
      }
    }
    // A new entry here means a new sticky element: it must get a dedicated
    // parent that ends before the next section, a z-index below the header
    // and a `position: static` reset below its desktop breakpoint.
    expect([...selectors].sort()).toEqual([
      ".account__nav",
      ".cart-page__summary",
      ".checkout__summary",
      ".shop__sidebar",
      ".site-header",
    ]);
  });

  it("gives the cart/checkout wrappers their own stacking context", () => {
    const rules = parseCss();
    for (const wrapper of [".cart-page__body", ".checkout__body"]) {
      const declarations = effectiveDeclarations(rules, wrapper);
      expect(declarations.position, `${wrapper}.position`).toBe("relative");
      expect(declarations["z-index"], `${wrapper}.z-index`).toBe("0");
    }
  });

  it("keeps every sticky element in a clear z-index order", () => {
    const rules = parseCss();
    const zOf = (selector) => {
      const value = effectiveDeclarations(rules, selector)["z-index"];
      return value === undefined ? null : Number(value);
    };
    const header = zOf(".site-header");
    expect(header).toBe(60);
    for (const selector of [".cart-page__summary", ".checkout__summary", ".shop__sidebar", ".account__nav"]) {
      expect(zOf(selector), `${selector}.z-index`).toBeGreaterThan(0);
      expect(zOf(selector), `${selector} must stay under the sticky header`).toBeLessThan(header);
    }
    // The overlays keep the item-1 ladder: contact < drawer < mini-cart < toaster.
    expect(zOf(".floating-contact")).toBeLessThan(zOf(".site-header__drawer"));
    expect(zOf(".site-header__drawer")).toBeLessThan(zOf(".minicart"));
    expect(zOf(".minicart")).toBeLessThan(zOf(".toaster"));
  });

  it("turns sticky off below the desktop breakpoint for every sticky element", () => {
    const rules = parseCss();
    // selector -> the media query it must be reset in
    const OFF_AT = {
      ".shop__sidebar": "(max-width: 1024px)",
      ".cart-page__summary": "(max-width: 768px)",
      ".checkout__summary": "(max-width: 768px)",
      ".account__nav": "(max-width: 768px)",
    };
    for (const [selector, media] of Object.entries(OFF_AT)) {
      const declarations = effectiveDeclarations(rules, selector, media);
      expect(declarations.position, `${selector} must be static in @media ${media}`).toBe("static");
    }
    // ...and the sticky wrappers are not reset anywhere (the summary inside
    // them is what loses sticky on small screens).
    for (const wrapper of [".cart-page__body", ".checkout__body"]) {
      const resets = rules.filter(
        (rule) => rule.media && rule.selectors.includes(wrapper) && rule.declarations.position === "static"
      );
      expect(resets, `${wrapper} must not be reset in a media query`).toEqual([]);
    }
  });
});
