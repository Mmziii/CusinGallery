import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CategoryFilterTree from "./CategoryFilterTree";

const categories = [
  { id: 1, name: "آشپزخانه", slug: "kitchen-root", is_catalog_root: true, parent: null, parent_slug: null },
  { id: 2, name: "ظروف پخت", slug: "cookware", parent: 1, parent_slug: "kitchen-root" },
  { id: 3, name: "قابلمه", slug: "pots", parent: 2, parent_slug: "cookware" },
  { id: 4, name: "قابلمه گرانیتی", slug: "granite", parent: 3, parent_slug: "pots" },
  { id: 5, name: "بلور", slug: "glass", parent: 1, parent_slug: "kitchen-root" },
  { id: 6, name: "دسته قدیمی", slug: "kitchen", is_catalog_root: false, parent: 1, parent_slug: "kitchen-root" },
];
afterEach(cleanup);

describe("category filter tree", () => {
  it("shows main groups with independent expand arrows and selectable parents", () => {
    const onChange = vi.fn();
    render(<CategoryFilterTree categories={categories} selected="" onChange={onChange} />);
    expect(screen.queryByRole("radio", { name: "آشپزخانه" })).toBeNull();
    expect(screen.getByRole("radio", { name: "دسته قدیمی" })).toBeTruthy();
    expect(screen.queryByRole("radio", { name: "قابلمه" })).toBeNull();
    const toggle = screen.getByRole("button", { name: "زیردسته‌های ظروف پخت" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(screen.getByRole("radio", { name: "قابلمه" })).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("radio", { name: "ظروف پخت" }));
    expect(onChange).toHaveBeenCalledWith("cookware");
  });

  it("opens the full ancestor path for an existing deep selection", () => {
    render(<CategoryFilterTree categories={categories} selected="granite" onChange={vi.fn()} />);
    expect(screen.getByRole("radio", { name: "قابلمه گرانیتی" }).checked).toBe(true);
    expect(screen.getByRole("button", { name: "زیردسته‌های ظروف پخت" }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("button", { name: "زیردسته‌های قابلمه" }).getAttribute("aria-expanded")).toBe("true");
  });

  it("retains categories whose parent is absent and can reset the selection", () => {
    const onChange = vi.fn();
    render(<CategoryFilterTree categories={[categories[4]]} selected="glass" onChange={onChange} />);
    expect(screen.getByRole("radio", { name: "بلور" }).checked).toBe(true);
    fireEvent.click(screen.getByRole("radio", { name: "همه دسته‌ها" }));
    expect(onChange).toHaveBeenCalledWith("");
  });
});
