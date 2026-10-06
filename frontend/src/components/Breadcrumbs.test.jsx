/**
 * Part S2 item 7: breadcrumb trail. Every entry but the last is a link;
 * the last one is plain text marked as the current page.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import Breadcrumbs from "./Breadcrumbs";

describe("Breadcrumbs (S2.7)", () => {
  it("links intermediate entries and marks the last as the current page", () => {
    render(
      <MemoryRouter>
        <Breadcrumbs
          items={[
            { label: "خانه", to: "/" },
            { label: "فروشگاه", to: "/shop/" },
            { label: "قابلمه گرانیتی", to: "/shop/?category=pots" },
            { label: "قابلمه گرانیتی ۲۸ سانتی" },
          ]}
        />
      </MemoryRouter>
    );

    expect(screen.getByRole("navigation", { name: "مسیر صفحه" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "خانه" }).getAttribute("href")).toBe("/");
    expect(screen.getByRole("link", { name: "فروشگاه" }).getAttribute("href")).toBe("/shop/");
    // The last entry is NOT a link and carries aria-current="page".
    const last = screen.getByText("قابلمه گرانیتی ۲۸ سانتی");
    expect(last.closest("a")).toBeNull();
    expect(last.getAttribute("aria-current")).toBe("page");
  });

  it("renders nothing for an empty trail", () => {
    const { container } = render(
      <MemoryRouter>
        <Breadcrumbs items={[]} />
      </MemoryRouter>
    );
    expect(container.querySelector(".breadcrumbs")).toBeNull();
  });
});
