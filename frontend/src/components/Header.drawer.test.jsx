import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import Header from "./Header";

const CATEGORY_TREE = [
  {
    id: 1,
    name: "آشپزخانه",
    slug: "kitchen-root",
    is_catalog_root: true,
    product_count: 1,
    children: [
      { id: 2, name: "ظروف پخت", slug: "cookware", product_count: 1, children: [] },
    ],
  },
];
const originalAdapter = apiClient.defaults.adapter;
let authenticatedUser = null;

function response(config, data) {
  return { data, status: 200, statusText: "OK", headers: {}, config };
}

function LocationProbe() {
  const { pathname } = useLocation();
  return <output data-testid="location">{pathname}</output>;
}

function renderHeader(route = "/") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Header />
      <LocationProbe />
    </MemoryRouter>
  );
}

beforeEach(() => {
  authenticatedUser = null;
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (url.startsWith("/categories/tree/")) {
      return response(config, { count: CATEGORY_TREE.length, next: null, previous: null, results: CATEGORY_TREE });
    }
    if (url.startsWith("/accounts/me/")) return response(config, { user: authenticatedUser, ...authenticatedUser });
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
});

async function openDrawer(view) {
  fireEvent.click(view.container.querySelector(".site-header__burger"));
  return screen.findByRole("dialog", { name: "منوی اصلی" });
}

describe("mobile navigation drawer", () => {
  it("shows only the requested links, highlights the current page and locks scrolling", async () => {
    const view = renderHeader("/shop/");
    const drawer = await openDrawer(view);

    const primaryNav = within(drawer).getByRole("navigation", { name: "ناوبری اصلی" });
    expect([...primaryNav.children].map((item) => item.textContent.trim())).toEqual([
      "خانه",
      "فروشگاه",
      "دسته‌بندی کالاها",
      "علاقه‌مندی‌ها",
      "سبد خرید",
      "دربارهٔ ما",
      "تماس با ما",
    ]);
    expect(within(drawer).getByRole("link", { name: "فروشگاه" }).getAttribute("aria-current")).toBe("page");
    expect(within(drawer).getByRole("link", { name: "ورود / ثبت‌نام" })).toBeTruthy();
    expect(within(drawer).queryByText("آشپزخانه")).toBeNull();
    expect(within(drawer).queryByText("ظروف پخت")).toBeNull();
    expect(document.body.classList.contains("body--scroll-locked")).toBe(true);

    within(drawer).getAllByRole("link").forEach((link) => {
      expect(link.querySelector(".icon")).not.toBeNull();
    });
  });

  it("opens the existing category sheet from the drawer item", async () => {
    const view = renderHeader();
    const drawer = await openDrawer(view);

    fireEvent.click(within(drawer).getByRole("button", { name: "دسته‌بندی کالاها" }));

    const sheet = await screen.findByRole("dialog", { name: "دسته‌بندی کالاها" });
    expect(within(sheet).getByRole("link", { name: /ظروف پخت/ })).toBeTruthy();
    expect(document.body.querySelector(".site-header__drawer")).toBeNull();
    expect(document.body.classList.contains("body--scroll-locked")).toBe(true);
  });

  it("closes on overlay click, Escape and route changes, including the reverse animation", async () => {
    const view = renderHeader();
    await openDrawer(view);
    fireEvent.click(document.body.querySelector(".site-header__drawer-backdrop"));
    expect(document.body.querySelector(".site-header__drawer").classList.contains("is-closing")).toBe(true);
    await waitFor(() => expect(document.body.querySelector(".site-header__drawer")).toBeNull());
    expect(document.body.classList.contains("body--scroll-locked")).toBe(false);

    let drawer = await openDrawer(view);
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(document.body.querySelector(".site-header__drawer")).toBeNull());

    drawer = await openDrawer(view);
    fireEvent.click(within(drawer).getByRole("link", { name: "تماس با ما" }));
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/contact/"));
    await waitFor(() => expect(document.body.querySelector(".site-header__drawer")).toBeNull());
  });

  it("shows account and sign-out actions for authenticated shoppers", async () => {
    authenticatedUser = { id: 9, first_name: "مریم", phone: "09120000000" };
    useAuthStore.setState({ user: authenticatedUser, isAuthenticated: true, isLoading: false, error: null });
    const view = renderHeader();
    const drawer = await openDrawer(view);

    expect(within(drawer).getByRole("link", { name: "حساب کاربری" })).toBeTruthy();
    expect(within(drawer).getByRole("button", { name: "خروج" })).toBeTruthy();
    expect(within(drawer).queryByRole("link", { name: "ورود / ثبت‌نام" })).toBeNull();
  });
});
