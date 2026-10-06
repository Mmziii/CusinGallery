/**
 * ErrorBoundary tests (Part R3): a throwing child renders the friendly
 * Persian fallback (never a blank page), retry re-renders the child, and
 * the back-home link is present.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import ErrorBoundary from "./ErrorBoundary";

function Boom() {
  throw new Error("boom");
}

afterEach(cleanup);

describe("ErrorBoundary", () => {
  it("shows the friendly fallback when a child crashes", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <MemoryRouter>
        <ErrorBoundary>
          <Boom />
        </ErrorBoundary>
      </MemoryRouter>
    );
    expect(screen.getByText("مشکلی پیش آمد")).toBeTruthy();
    expect(screen.getByText("تلاش دوباره")).toBeTruthy();
    expect(screen.getByText("بازگشت به صفحه اصلی").getAttribute("href")).toBe("/");
    spy.mockRestore();
  });

  it("renders children normally when nothing throws", () => {
    render(
      <MemoryRouter>
        <ErrorBoundary>
          <p>سالم</p>
        </ErrorBoundary>
      </MemoryRouter>
    );
    expect(screen.getByText("سالم")).toBeTruthy();
  });

  it("retry re-renders the child tree", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    let fail = true;
    function Flaky() {
      if (fail) throw new Error("flaky");
      return <p>بازیابی شد</p>;
    }
    render(
      <MemoryRouter>
        <ErrorBoundary>
          <Flaky />
        </ErrorBoundary>
      </MemoryRouter>
    );
    expect(screen.getByText("مشکلی پیش آمد")).toBeTruthy();
    fail = false;
    fireEvent.click(screen.getByText("تلاش دوباره"));
    expect(screen.getByText("بازیابی شد")).toBeTruthy();
    spy.mockRestore();
  });
});
