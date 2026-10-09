/**
 * Scrolled-header overlay regression coverage.
 *
 * Fixed drawers are direct children of document.body, and the compact-header
 * blur is intentionally painted by a sibling pseudo-element rather than by
 * `.site-header` itself. Together those rules prevent a shell ancestor from
 * capturing the fixed viewport during a scroll state.
 */
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import App from "../App.jsx";
import useCartStore from "../store/useCartStore";
import {
  containingBlockAncestor,
  fixedElements,
  winningDeclaration,
  CONTAINING_BLOCK_PROPS,
} from "../test/cssCascade";

const PRODUCT = {
  id: 11,
  name: "ست قابلمه ۶ پارچه گرانیتی",
  slug: "granite-set",
  price_info: { price: 1250000, compare_at_price: null, discount_percentage: 0, is_on_sale: false, discount_amount: 0 },
  primary_image: null,
  is_in_stock: true,
};

const originalAdapter = apiClient.defaults.adapter;
const originalInnerWidth = Object.getOwnPropertyDescriptor(window, "innerWidth");
const originalClientWidth = Object.getOwnPropertyDescriptor(document.documentElement, "clientWidth");

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    if (/site\/settings/.test(config.url || "")) {
      // a configured phone number makes the floating contact cluster render,
      // which is the element the drawer's checkout button must stay above
      return { data: { phone: "02112345678" }, status: 200, statusText: "OK", headers: {}, config };
    }
    if ((config.url || "") === "/products/") {
      return { data: { count: 1, next: null, previous: null, results: [PRODUCT] }, status: 200, statusText: "OK", headers: {}, config };
    }
    return originalAdapter(config);
  };
});

afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});

afterEach(() => {
  cleanup();
  useCartStore.setState({ guestLines: [], guestProducts: {}, guestHydration: "idle" });
  Object.defineProperty(window, "scrollY", { value: 0, configurable: true });
  if (originalInnerWidth) Object.defineProperty(window, "innerWidth", originalInnerWidth);
  if (originalClientWidth) Object.defineProperty(document.documentElement, "clientWidth", originalClientWidth);
  else delete document.documentElement.clientWidth;
});

const originalScrollY = window.scrollY;

/** Render the real app shell and put the header into its scrolled state
 *  (the state in which the owner saw the truncated drawer). */
/** One guest line, already hydrated from the (mocked) products API, so the
 *  drawer renders its item list and checkout button. */
function seedGuestCart() {
  useCartStore.setState({
    guestLines: [{ product_id: PRODUCT.id, variant_id: null, quantity: 2 }],
    guestProducts: { [PRODUCT.id]: PRODUCT },
    guestHydration: "ready",
  });
}

async function renderScrolled(route = "/") {
  seedGuestCart();
  const view = render(
    <MemoryRouter initialEntries={[route]}>
      <App />
    </MemoryRouter>
  );
  Object.defineProperty(window, "scrollY", { value: 300, configurable: true });
  fireEvent.scroll(window);
  await waitFor(() => expect(view.container.querySelector(".site-header--compact")).toBeTruthy());
  return view;
}

async function openMiniCart(view) {
  fireEvent.click(view.container.querySelector(".cart-link"));
  await waitFor(() => expect(document.body.querySelector(".minicart")).toBeTruthy());
  return document.body.querySelector(".minicart");
}

describe("full-viewport overlays while the page is scrolled", () => {
  it("keeps the compact header free of fixed-containing-block properties", async () => {
    const view = await renderScrolled();
    const header = view.container.querySelector(".site-header");
    expect(header.classList.contains("site-header--compact")).toBe(true);
    for (const property of CONTAINING_BLOCK_PROPS) {
      expect(winningDeclaration(header, property), `${property} on the header`).toBeNull();
    }
  });

  it("renders the mini-cart drawer outside the header, as a child of body", async () => {
    const view = await renderScrolled();
    const drawer = await openMiniCart(view);

    expect(drawer.closest(".site-header")).toBeNull();
    expect(drawer.closest("header")).toBeNull();
    expect(drawer.parentElement).toBe(document.body);
    // full-viewport overlay class survives the portal
    expect(drawer.classList.contains("minicart")).toBe(true);
    expect(drawer.querySelector(".minicart__backdrop")).toBeTruthy();
    expect(drawer.querySelector(".minicart__panel")).toBeTruthy();

    // and no fixed-position element anywhere in the app is inside a
    // filtered/transformed ancestor any more
    const captured = fixedElements(document.body).filter((el) => containingBlockAncestor(el));
    expect(captured.map((el) => el.className)).toEqual([]);
  });

  it("keeps every header drawer a direct document.body child in compact scroll state", async () => {
    const view = await renderScrolled();
    const miniCart = await openMiniCart(view);
    expect(miniCart.parentElement).toBe(document.body);

    fireEvent.click(miniCart.querySelector(".minicart__backdrop"));
    await waitFor(() => expect(document.body.querySelector(".minicart")).toBeNull());
    fireEvent.click(view.container.querySelector(".site-header__burger"));
    await waitFor(() => expect(document.body.querySelector(".site-header__drawer")).toBeTruthy());
    expect(document.body.querySelector(".site-header__drawer").parentElement).toBe(document.body);
  });

  it("locks page scrolling without losing the scrollbar gutter", async () => {
    Object.defineProperty(window, "innerWidth", { value: 1200, configurable: true });
    Object.defineProperty(document.documentElement, "clientWidth", { value: 1184, configurable: true });
    const view = await renderScrolled();
    const drawer = await openMiniCart(view);

    expect(document.body.classList.contains("body--scroll-locked")).toBe(true);
    expect(document.documentElement.classList.contains("html--scroll-locked")).toBe(true);
    expect(document.body.style.getPropertyValue("--overlay-scrollbar-compensation")).toBe("16px");

    fireEvent.click(drawer.querySelector(".minicart__backdrop"));
    await waitFor(() => expect(document.body.querySelector(".minicart")).toBeNull());
    expect(document.body.classList.contains("body--scroll-locked")).toBe(false);
    expect(document.documentElement.classList.contains("html--scroll-locked")).toBe(false);
    expect(document.body.style.getPropertyValue("--overlay-scrollbar-compensation")).toBe("");
  });

  it("renders the mobile navigation drawer outside the header too", async () => {
    const view = await renderScrolled();
    fireEvent.click(view.container.querySelector(".site-header__burger"));
    await waitFor(() => expect(document.body.querySelector(".site-header__drawer")).toBeTruthy());
    const drawer = document.body.querySelector(".site-header__drawer");
    expect(drawer.closest(".site-header")).toBeNull();
    expect(drawer.parentElement).toBe(document.body);
  });

  it("keeps the focus trap, Escape and focus restore working through the portal", async () => {
    const view = await renderScrolled();
    const trigger = view.container.querySelector(".cart-link");
    trigger.focus();
    const drawer = await openMiniCart(view);

    await waitFor(() => expect(drawer.contains(document.activeElement)).toBe(true));
    const panel = drawer.querySelector(".minicart__panel");
    expect(panel.contains(document.activeElement)).toBe(true);

    fireEvent.keyDown(document.activeElement, { key: "Escape" });
    await waitFor(() => expect(document.body.querySelector(".minicart")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("keeps the drawer's checkout button above the floating contact cluster", async () => {
    const view = await renderScrolled();
    const drawer = await openMiniCart(view);
    const checkout = drawer.querySelector(".minicart__foot a");
    expect(checkout.getAttribute("href")).toBe("/cart/");

    // z-index ladder: floating contact < drawers < toaster. Both are
    // position: fixed and portaled to <body>, so the higher z-index wins.
    const contact = view.container.querySelector(".floating-contact")
      || document.body.querySelector(".floating-contact");
    expect(contact).toBeTruthy();
    const drawerZ = Number(winningDeclaration(drawer, "z-index")?.value || 0);
    const contactZ = Number(winningDeclaration(contact, "z-index")?.value || 0);
    expect(drawerZ).toBeGreaterThan(contactZ);
    // the drawer's z-index must not be raised above the toaster either
    const toaster = view.container.querySelector(".toaster") || document.body.querySelector(".toaster");
    if (toaster) expect(drawerZ).toBeLessThan(Number(winningDeclaration(toaster, "z-index")?.value || 0));
  });

  it("never leaves a fixed overlay inside a filter/transform ancestor (every page)", async () => {
    // Structural sweep over the whole app: for each storefront page the
    // fixed-position elements that exist (toaster, floating contact, the
    // product page's mobile buy bar, the drawers once opened) must not sit
    // under an ancestor that creates a containing block. This is the
    // general guard for the whole class of bug, not just the two drawers.
    expect(CONTAINING_BLOCK_PROPS).toContain("backdrop-filter");
    for (const route of ["/", "/shop/", "/cart/", "/login/"]) {
      cleanup();
      const view = render(
        <MemoryRouter initialEntries={[route]}>
          <App />
        </MemoryRouter>
      );
      await waitFor(() => expect(view.container.querySelector(".site-header")).toBeTruthy());
      for (const el of fixedElements(document.body)) {
        expect(containingBlockAncestor(el), `${el.className} on ${route} is captured`).toBeNull();
      }
    }
    Object.defineProperty(window, "scrollY", { value: originalScrollY, configurable: true });
  });
});
