/*
 * The logo/name is the storefront's universal recovery control. These tests
 * mount the real Header with its router, portals and asynchronous search so
 * the assertions cover navigation and surface cleanup rather than link hrefs.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MainLayout from "../layouts/MainLayout.jsx";
import apiClient from "../services/apiClient";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import Header from "./Header.jsx";

const CATEGORY = { id: 1, name: "ظروف پخت", slug: "cookware", children: [] };
const PRODUCT = {
  id: 7,
  name: "قابلمه آزمایشی",
  slug: "test-pot",
  primary_image: null,
  price_info: null,
};
const originalAdapter = apiClient.defaults.adapter;
const originalMatchMedia = window.matchMedia;

function response(config, data) {
  return { data, status: 200, statusText: "OK", headers: {}, config };
}

function LocationProbe() {
  const { pathname, search, hash } = useLocation();
  return <output data-testid="location">{`${pathname}${search}${hash}`}</output>;
}

function renderHeader(route = "/") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Header />
      <LocationProbe />
    </MemoryRouter>
  );
}

function BrokenCheckoutRoute() {
  throw new Error("checkout route crashed");
}

beforeEach(() => {
  apiClient.defaults.adapter = async (config) => {
    if ((config.url || "").startsWith("/categories/tree/")) {
      return response(config, { count: 1, next: null, previous: null, results: [CATEGORY] });
    }
    if ((config.url || "") === "/products/") {
      return response(config, { count: 1, next: null, previous: null, results: [PRODUCT] });
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
  window.matchMedia = originalMatchMedia;
  Object.defineProperty(window, "scrollY", { value: 0, configurable: true });
  vi.restoreAllMocks();
});

describe("home brand navigation", () => {
  it.each([
    ["404", "/missing-page/?from=header#lost"],
    ["checkout", "/checkout/?step=delivery#address"],
    ["payment result", "/payment/result/51/?state=ok#receipt"],
    ["account", "/account/orders/?page=2#history"],
  ])("goes home and removes query/hash from %s", async (_kind, route) => {
    const view = renderHeader(route);
    const brand = view.container.querySelector(".site-header__inner > .site-header__brand");

    fireEvent.click(brand);

    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/"));
  });

  it("closes every header surface and clears a pending search from the drawer home link", async () => {
    const view = renderHeader("/account/orders/?page=2#history");
    const search = view.container.querySelector('input[type="search"]');
    fireEvent.change(search, { target: { value: "قابلمه" } });
    await waitFor(() => expect(view.container.querySelector(".search-suggest")).toBeTruthy());

    const megaButton = screen.getByRole("button", { name: /دسته‌بندی کالاها/ });
    fireEvent.click(megaButton);
    await waitFor(() => expect(view.container.querySelector(".mega-menu")).toBeTruthy());

    fireEvent.click(view.container.querySelector(".cart-link"));
    await waitFor(() => expect(document.body.querySelector(".minicart")).toBeTruthy());

    fireEvent.click(view.container.querySelector(".site-header__burger"));
    const drawer = await waitFor(() => {
      const node = document.body.querySelector(".site-header__drawer");
      expect(node).toBeTruthy();
      return node;
    });
    // The full-viewport drawer covers the header, so it exposes its own
    // keyboard-accessible logo/name action instead of hiding the way home.
    const drawerBrand = drawer.querySelector('a[aria-label="کازین گالری — صفحه اصلی"]');
    expect(drawerBrand).toBeTruthy();
    expect(document.body.querySelector(".minicart__brand")).toBeTruthy();
    drawerBrand.focus();
    expect(document.activeElement).toBe(drawerBrand);

    fireEvent.click(drawerBrand);

    await waitFor(() => {
      expect(screen.getByTestId("location").textContent).toBe("/");
      expect(document.body.querySelector(".site-header__drawer")).toBeNull();
      expect(document.body.querySelector(".minicart")).toBeNull();
      expect(view.container.querySelector(".mega-menu")).toBeNull();
      expect(view.container.querySelector(".search-suggest")).toBeNull();
      expect(search.value).toBe("");
    });
  });

  it.each([
    [false, "smooth"],
    [true, "auto"],
  ])("scrolls an already-home page to the top with reduced motion set to %s", (reduced, behavior) => {
    Object.defineProperty(window, "scrollY", { value: 360, configurable: true });
    window.matchMedia = vi.fn(() => ({ matches: reduced }));
    const scrollTo = vi.spyOn(window, "scrollTo");
    const view = renderHeader("/?campaign=autumn#offers");

    fireEvent.click(view.container.querySelector(".site-header__inner > .site-header__brand"));

    expect(scrollTo).toHaveBeenCalledWith({ top: 0, left: 0, behavior });
  });

  it("keeps the logo/name usable from a route error fallback", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <MemoryRouter initialEntries={["/checkout/?step=delivery#address"]}>
        <Routes>
          <Route element={<MainLayout />}>
            <Route path="/checkout/" element={<BrokenCheckoutRoute />} />
            <Route path="/" element={<h1>خانه بازیابی‌شده</h1>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText("مشکلی پیش آمد")).toBeTruthy();
    fireEvent.click(screen.getByRole("link", { name: "کازین گالری — صفحه اصلی" }));
    expect(await screen.findByRole("heading", { name: "خانه بازیابی‌شده" })).toBeTruthy();
    spy.mockRestore();
  });
});
