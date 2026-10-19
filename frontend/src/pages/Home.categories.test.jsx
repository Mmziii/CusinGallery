import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import Home from "./Home";

const originalAdapter = apiClient.defaults.adapter;
const GROUPS = [
  { id: 2, name: "ظروف پخت", slug: "cookware", is_catalog_root: false, children: [] },
  { id: 3, name: "دسته قدیمی", slug: "kitchen", is_catalog_root: false, children: [] },
];

beforeEach(() => {
  apiClient.defaults.adapter = async (config) => {
    if ((config.url || "").includes("/categories/tree/")) {
      return {
        data: { count: 1, next: null, previous: null, results: [{ id: 1, name: "آشپزخانه", slug: "kitchen-root-2", is_catalog_root: true, children: GROUPS }] },
        status: 200, statusText: "OK", headers: {}, config,
      };
    }
    return originalAdapter(config);
  };
});
afterEach(() => { cleanup(); apiClient.defaults.adapter = originalAdapter; });

describe("home category tiles", () => {
  it("shows the real root's children, including a legacy kitchen-slug group, instead of one root tile", async () => {
    const { container } = render(<MemoryRouter><Home /></MemoryRouter>);
    await screen.findByRole("heading", { name: "دسته‌بندی‌ها" });
    const tiles = [...container.querySelectorAll(".category-card")];
    expect(tiles.map((tile) => tile.textContent)).toEqual(["ظروف پخت", "دسته قدیمی"]);
    expect(tiles.map((tile) => tile.getAttribute("href"))).toEqual(["/shop/?category=cookware", "/shop/?category=kitchen"]);
  });
});
