import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BrandFilter from "./BrandFilter";

const brands = [
  { id: 1, name: "یونیک", slug: "unique" },
  { id: 2, name: "كريستال", slug: "crystal" },
];
afterEach(cleanup);

describe("brand list search", () => {
  it("filters as you type with Persian/Arabic ی and ک normalized in both directions", () => {
    const onChange = vi.fn();
    render(<BrandFilter brands={brands} selected="unique" onChange={onChange} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "يونيك" } });
    expect(screen.getByRole("radio", { name: "یونیک" }).checked).toBe(true);
    expect(screen.queryByRole("radio", { name: "كريستال" })).toBeNull();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "کریستال" } });
    expect(screen.getByRole("radio", { name: "كريستال" })).toBeTruthy();
    expect(screen.queryByRole("radio", { name: "یونیک" })).toBeNull();
    expect(onChange).not.toHaveBeenCalled(); // searching does not change the product filter
    fireEvent.click(screen.getByRole("radio", { name: "كريستال" }));
    expect(onChange).toHaveBeenCalledWith("crystal");
  });

  it("shows the requested empty message, then restores the selected brand when cleared", () => {
    render(<BrandFilter brands={brands} selected="unique" onChange={vi.fn()} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "وجود ندارد" } });
    expect(screen.getByRole("status").textContent).toBe("موردی پیدا نشد");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "" } });
    expect(screen.getByRole("radio", { name: "یونیک" }).checked).toBe(true);
  });

  it("keeps the route's brand locked on brand pages", () => {
    render(<BrandFilter brands={[brands[0]]} selected="unique" onChange={vi.fn()} locked />);
    expect(screen.getByRole("radio").disabled).toBe(true);
    expect(screen.getByRole("radio").checked).toBe(true);
    expect(screen.queryByRole("radio", { name: "همه برندها" })).toBeNull();
  });
});
