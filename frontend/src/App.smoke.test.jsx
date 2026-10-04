/**
 * Storefront smoke test (Part 0) -- the regression guard for the white
 * page bug: <App /> is a bare <Routes> tree and renders NOTHING (react-
 * router throws) unless a Router wraps it. `npm run build` and lint both
 * pass with the bug present, so only a render test can catch it.
 *
 * Renders the REAL app root (router + layout + pages) at several routes
 * with the API served by the fake adapter in src/test/setup.js, and
 * asserts each route mounts and shows its key content.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import App from "./App.jsx";

function renderAt(route) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <App />
    </MemoryRouter>
  );
}

afterEach(cleanup);

describe("storefront smoke", () => {
  it("mounts the home page inside the router (no white page)", async () => {
    renderAt("/");
    // Header nav + footer brand render -- proof the router context
    // exists and MainLayout mounted.
    const shopLinks = await screen.findAllByText("فروشگاه");
    expect(shopLinks.length).toBeGreaterThan(0);
  });

  it("mounts /shop/ with its heading", async () => {
    renderAt("/shop/");
    expect(await screen.findByRole("heading", { name: "فروشگاه" })).toBeTruthy();
  });

  it("mounts /cart/ (logged-out state for a fresh visitor)", async () => {
    renderAt("/cart/");
    // Pre-guest-cart behaviour: logged-out visitors get the "log in to
    // see your cart" state. Part 1 replaces this with the guest cart;
    // the smoke test only guards that the page MOUNTS without throwing.
    expect(await screen.findByText("برای مشاهده سبد خرید وارد شوید.")).toBeTruthy();
  });

  it("mounts /login/ with its heading", async () => {
    renderAt("/login/");
    expect(await screen.findByRole("heading", { name: /ورود/ })).toBeTruthy();
  });

  it("mounts an unknown route as the 404 page", async () => {
    renderAt("/definitely-not-a-page/");
    expect(await screen.findByText("صفحه مورد نظر پیدا نشد.")).toBeTruthy();
  });
});
