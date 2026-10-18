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
            { label: "کازین گالری", to: "/" },
            { label: "آشپزخانه", to: "/shop/" },
            { label: "قاشق، چنگال و کارد", to: "/shop/?category=cutlery" },
            { label: "قاشق چایی", to: "/shop/?category=tea-spoons" },
            { label: "قاشق چایی طلایی" },
          ]}
        />
      </MemoryRouter>
    );

    expect(screen.getByRole("navigation", { name: "مسیر صفحه" })).toBeTruthy();
    // Stage 1: the trail starts at the BRAND (کازین گالری,
    // linking home) -- not «خانه» -- then «آشپزخانه»,
    // then the deeper levels.
    expect(screen.getByRole("link", { name: "کازین گالری" }).getAttribute("href")).toBe("/");
    expect(screen.getByRole("link", { name: "آشپزخانه" }).getAttribute("href")).toBe("/shop/");
    expect(screen.getByRole("link", { name: "قاشق، چنگال و کارد" }).getAttribute("href")).toBe(
      "/shop/?category=cutlery"
    );
    expect(screen.getByRole("link", { name: "قاشق چایی" }).getAttribute("href")).toBe(
      "/shop/?category=tea-spoons"
    );
    // The last entry is NOT a link and carries aria-current="page".
    const last = screen.getByText("قاشق چایی طلایی");
    expect(last.closest("a")).toBeNull();
    expect(last.getAttribute("aria-current")).toBe("page");
  });

  it("starts every storefront trail with کازین گالری › آشپزخانه", () => {
    const view = render(
      <MemoryRouter>
        <Breadcrumbs
          items={[
            { label: "کازین گالری", to: "/" },
            { label: "آشپزخانه", to: "/shop/" },
            { label: "قابلمه گرانیتی ۲۸ سانتی" },
          ]}
        />
      </MemoryRouter>
    );
    // Scoped to THIS render (the file has no global
    // cleanup, so earlier trails are still in the DOM).
    const labels = [...view.container.querySelectorAll("li")].map(
      (item) => item.textContent
    );
    expect(labels).toEqual(["کازین گالری", "آشپزخانه", "قابلمه گرانیتی ۲۸ سانتی"]);
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
