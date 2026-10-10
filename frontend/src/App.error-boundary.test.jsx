/* The app-level boundary is the last recovery layer if the shell itself
 * fails before MainLayout can mount its narrower Outlet boundary. */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./layouts/MainLayout.jsx", () => ({
  default: function BrokenLayout() {
    throw new Error("shell crashed");
  },
}));

import App from "./App.jsx";

afterEach(cleanup);

describe("app-level error boundary", () => {
  it("shows recovery links when the layout itself throws", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByRole("alert").textContent).toContain("مشکلی پیش آمد");
    expect(screen.getByRole("link", { name: "بازگشت به صفحه اصلی" }).getAttribute("href")).toBe("/");
    expect(screen.getByRole("link", { name: "رفتن به فروشگاه" }).getAttribute("href")).toBe("/shop/");
    spy.mockRestore();
  });
});
