/**
 * Part S5 follow-up 4, item 1: "the mini-cart drawer is truncated when the
 * page is scrolled".
 *
 * Reproduced mechanism (real, spec-level, not a status code): the drawers
 * used to be rendered inside <header class="site-header">. From scrollY > 24
 * the header carries `.site-header--compact`, whose `backdrop-filter:
 * blur(12px)` makes the header a CONTAINING BLOCK for its fixed
 * descendants, so `position: fixed; inset: 0` resolved against the header's
 * ~60-76px box instead of the viewport: the drawer collapsed, its list got
 * a scrollbar and the checkout button spilled out of the panel. At the top
 * of the page there is no blur, which is why it only happened while
 * scrolled.
 *
 * The drawer is now portaled into document.body (components/Portal.jsx), so
 * no filtered ancestor can capture it in any scroll state.
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
  it("reproduces the scrolled state that triggered the bug (header is blurred)", async () => {
    const view = await renderScrolled();
    const header = view.container.querySelector(".site-header");
    // The header really is in the state that creates a containing block.
    expect(header.classList.contains("site-header--compact")).toBe(true);
    const blur = winningDeclaration(header, "backdrop-filter") || winningDeclaration(header, "-webkit-backdrop-filter");
    expect(blur?.value).toMatch(/blur/);
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
