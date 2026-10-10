/*
 * A route-level crash must not make its fallback permanent. The real layout
 * keeps the header outside its Outlet boundary, so its logo and primary nav
 * are the two recovery paths a shopper actually has after a bad route.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MainLayout from "./MainLayout";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";

function BrokenRoute() {
  throw new Error("route crashed");
}

function SearchRoute() {
  const location = useLocation();
  if (location.search.includes("broken")) throw new Error("search route crashed");
  return <h1>جستجوی بازیابی‌شده</h1>;
}

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/broken/" element={<BrokenRoute />} />
          <Route path="/" element={<h1>خانهٔ بازیابی‌شده</h1>} />
          <Route path="/shop/" element={<SearchRoute />} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, error: null });
  useCartStore.setState({
    cart: null,
    guestLines: [],
    guestProducts: {},
    guestVariants: {},
    guestHydration: "ready",
    guestHydrationError: null,
    error: null,
  });
});

afterEach(() => cleanup());

describe("route error recovery navigation", () => {
  it("resets the route boundary after navigating with the header logo", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    renderAt("/broken/");
    expect(await screen.findByText("مشکلی پیش آمد")).toBeTruthy();

    fireEvent.click(screen.getByRole("link", { name: "کازین گالری — صفحه اصلی" }));

    expect(await screen.findByRole("heading", { name: "خانهٔ بازیابی‌شده" })).toBeTruthy();
    expect(screen.queryByText("مشکلی پیش آمد")).toBeNull();
    spy.mockRestore();
  });

  it("resets the route boundary after navigating with primary navigation", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    renderAt("/broken/");
    expect(await screen.findByText("مشکلی پیش آمد")).toBeTruthy();

    const header = document.querySelector(".site-header");
    fireEvent.click(within(header).getByRole("link", { name: "فروشگاه" }));

    expect(await screen.findByRole("heading", { name: "جستجوی بازیابی‌شده" })).toBeTruthy();
    expect(screen.queryByText("مشکلی پیش آمد")).toBeNull();
    spy.mockRestore();
  });

  it("also resets after header search changes only the query string", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    renderAt("/shop/?broken=1");
    expect(await screen.findByText("مشکلی پیش آمد")).toBeTruthy();

    const search = screen.getByRole("searchbox", { name: "جستجوی محصول" });
    fireEvent.change(search, { target: { value: "قابلمه" } });
    fireEvent.submit(search.closest("form"));

    expect(await screen.findByRole("heading", { name: "جستجوی بازیابی‌شده" })).toBeTruthy();
    expect(screen.queryByText("مشکلی پیش آمد")).toBeNull();
    spy.mockRestore();
  });
});
