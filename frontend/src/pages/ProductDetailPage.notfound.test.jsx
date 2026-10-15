import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
vi.mock("../hooks/useAsync", () => ({ useAsync: () => ({ data: null, isLoading: false, error: { response: { status: 404 } } }) }));
import ProductDetailPage from "./ProductDetailPage";
it("renders the branded not-found page for a missing product", () => {
  render(<MemoryRouter><ProductDetailPage /></MemoryRouter>);
  expect(screen.getByRole("heading", { name: "۴۰۴" })).toBeTruthy();
  expect(document.title).toContain("صفحه یافت نشد");
  expect(screen.queryByText(/ارتباط با سرور/)).toBeNull();
});
