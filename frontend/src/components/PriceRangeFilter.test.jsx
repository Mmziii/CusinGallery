import fs from "node:fs";
import path from "node:path";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PriceRangeFilter from "./PriceRangeFilter";

const bounds = { min: 75000, max: 12000000 };
const defaultProps = { bounds, resultRange: bounds, minimum: "", maximum: "", scopeKey: "shop" };
const minHandle = () => screen.getByRole("slider", { name: "کمترین قیمت" });
const maxHandle = () => screen.getByRole("slider", { name: "بیشترین قیمت" });
const advance = (milliseconds = 300) => act(() => vi.advanceTimersByTime(milliseconds));

beforeEach(() => vi.useFakeTimers());
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("RTL dual-handle price range", () => {
  it("uses one rail, two native handles and grouped Persian selected/result prices", () => {
    const { container } = render(<PriceRangeFilter {...defaultProps} onApply={vi.fn()} />);
    expect(container.querySelectorAll(".price-range__rail").length).toBe(1);
    expect(screen.getAllByRole("slider").length).toBe(2);
    expect(screen.getByText("از ۷۵٬۰۰۰ تا ۱۲٬۰۰۰٬۰۰۰ تومان")).toBeTruthy();
    expect(screen.getByText("ارزان‌ترین: ۷۵٬۰۰۰ تومان — گران‌ترین: ۱۲٬۰۰۰٬۰۰۰ تومان")).toBeTruthy();
    expect(minHandle().getAttribute("aria-valuetext")).toBe("۷۵٬۰۰۰ تومان");
    expect(minHandle().closest("[dir]").dir).toBe("rtl");
  });

  it("keeps dragging local and applies only after release plus the debounce", () => {
    const onApply = vi.fn();
    render(<PriceRangeFilter {...defaultProps} onApply={onApply} />);
    fireEvent.pointerDown(minHandle(), { pointerId: 1 });
    fireEvent.change(minHandle(), { target: { value: "100000" } });
    fireEvent.change(minHandle(), { target: { value: "200000" } });
    advance(1000);
    expect(onApply).not.toHaveBeenCalled();
    fireEvent.pointerUp(minHandle(), { pointerId: 1 });
    advance(299);
    expect(onApply).not.toHaveBeenCalled();
    advance(1);
    expect(onApply).toHaveBeenCalledExactlyOnceWith({ min: 200000, max: null });
  });

  it("applies both thumb values atomically when drags happen within the debounce window", () => {
    const onApply = vi.fn();
    render(<PriceRangeFilter {...defaultProps} onApply={onApply} />);
    fireEvent.pointerDown(minHandle());
    fireEvent.change(minHandle(), { target: { value: "100000" } });
    fireEvent.pointerUp(minHandle());
    advance(100);
    fireEvent.pointerDown(maxHandle());
    fireEvent.change(maxHandle(), { target: { value: "500000" } });
    fireEvent.pointerUp(maxHandle());
    advance();
    expect(onApply).toHaveBeenCalledExactlyOnceWith({ min: 100000, max: 500000 });
  });

  it("supports touch without sending requests while the handle is moving", () => {
    const onApply = vi.fn();
    render(<PriceRangeFilter {...defaultProps} onApply={onApply} />);
    fireEvent.touchStart(maxHandle());
    fireEvent.change(maxHandle(), { target: { value: "1000000" } });
    advance(500);
    expect(onApply).not.toHaveBeenCalled();
    fireEvent.touchEnd(maxHandle());
    advance();
    expect(onApply).toHaveBeenCalledExactlyOnceWith({ min: null, max: 1000000 });
  });

  it("makes left more expensive and right cheaper, with keyboard-accessible bounded values", () => {
    const onApply = vi.fn();
    render(<PriceRangeFilter {...defaultProps} onApply={onApply} />);
    fireEvent.keyDown(minHandle(), { key: "ArrowLeft" });
    expect(Number(minHandle().value)).toBeGreaterThan(bounds.min);
    expect(onApply).not.toHaveBeenCalled();
    fireEvent.keyUp(minHandle(), { key: "ArrowLeft" });
    advance();
    expect(onApply).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(minHandle(), { key: "ArrowRight" });
    expect(Number(minHandle().value)).toBe(bounds.min);
    fireEvent.keyDown(minHandle(), { key: "End" });
    expect(Number(minHandle().value)).toBe(bounds.max);
    fireEvent.keyDown(maxHandle(), { key: "Home" });
    expect(Number(maxHandle().value)).toBe(bounds.max); // cannot cross the other thumb
  });

  it("keeps both thumbs ordered even when native/assistive input tries to cross them", () => {
    render(<PriceRangeFilter {...defaultProps} minimum="100000" maximum="500000" onApply={vi.fn()} />);
    fireEvent.change(minHandle(), { target: { value: "900000" } });
    expect(minHandle().value).toBe("500000");
    fireEvent.change(maxHandle(), { target: { value: "75000" } });
    expect(maxHandle().value).toBe("500000");
    expect(minHandle().getAttribute("aria-valuemax")).toBe("500000");
    expect(maxHandle().getAttribute("aria-valuemin")).toBe("500000");
  });

  it("synchronizes back/forward filters and cancels pending changes from the old scope", () => {
    const onApply = vi.fn();
    const { rerender } = render(<PriceRangeFilter {...defaultProps} onApply={onApply} />);
    fireEvent.change(minHandle(), { target: { value: "200000" } });
    rerender(<PriceRangeFilter {...defaultProps} minimum="150000" maximum="500000" scopeKey="category=other" onApply={onApply} />);
    expect(minHandle().value).toBe("150000");
    expect(maxHandle().value).toBe("500000");
    advance();
    expect(onApply).not.toHaveBeenCalled();
  });

  it("keeps a usable domain when the selected range has no results", () => {
    render(<PriceRangeFilter {...defaultProps} minimum="13000000" resultRange={{ min: null, max: null }} onApply={vi.fn()} />);
    expect(minHandle().disabled).toBe(false);
    expect(screen.getByText("محصولی در این محدوده پیدا نشد.")).toBeTruthy();
    expect(minHandle().value).toBe("13000000");
    expect(maxHandle().value).toBe("13000000");
  });

  it("handles empty and single-price result sets without NaN or fabricated prices", () => {
    const { rerender, container } = render(<PriceRangeFilter {...defaultProps} bounds={{ min: null, max: null }} resultRange={{ min: null, max: null }} onApply={vi.fn()} />);
    expect(screen.getAllByRole("slider").every((handle) => handle.disabled)).toBe(true);
    rerender(<PriceRangeFilter {...defaultProps} bounds={{ min: 0, max: 0 }} resultRange={{ min: 0, max: 0 }} onApply={vi.fn()} />);
    expect(screen.getByText("از ۰ تا ۰ تومان")).toBeTruthy();
    expect(screen.getAllByRole("slider").every((handle) => handle.disabled)).toBe(true);
    expect(container.innerHTML).not.toContain("NaN");
  });

  it("has a single RTL track and draggable, separately focusable touch handles", () => {
    const css = fs.readFileSync(path.resolve(__dirname, "../styles/storefront.css"), "utf8");
    expect(css).toMatch(/\.price-range__input\s*\{[^}]*direction: rtl/);
    expect(css).toMatch(/::-webkit-slider-thumb\s*\{[^}]*pointer-events: auto/);
    expect(css).toMatch(/::-moz-range-thumb\s*\{[^}]*pointer-events: auto/);
  });
});
