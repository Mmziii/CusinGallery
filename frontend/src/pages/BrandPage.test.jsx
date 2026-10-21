import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import BrandPage from "./BrandPage";

const brand = { id: 1, name: "یونیک", slug: "یونیک", logo: "/media/brands/unique.jpg" };
const product = (id) => ({
  id, name: `قابلمه ${id}`, slug: `pot-${id}`, brand,
  price_info: { price: 75000, compare_at_price: null }, stock_status: "in_stock",
});
let requests = [];
let missing = false;
const originalAdapter = apiClient.defaults.adapter;
const originalMatchMedia = window.matchMedia;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const ok = (data) => ({ data, status: 200, statusText: "OK", headers: {}, config });
    if (config.url === `/brands/${brand.slug}/`) {
      if (missing) throw Object.assign(new Error("not found"), { response: { status: 404 } });
      return ok(brand);
    }
    if (config.url === "/brands/") return ok({ count: 1, next: null, results: [brand] });
    if (config.url === "/products/") {
      requests.push(config.params);
      return ok({ count: 21, next: config.params.page === 2 ? null : "?page=2", previous: null,
        results: [product(config.params.page === 2 ? 2 : 1)] });
    }
    return originalAdapter(config);
  };
});
afterAll(() => { apiClient.defaults.adapter = originalAdapter; });
afterEach(() => {
  cleanup();
  window.matchMedia = originalMatchMedia;
  requests = [];
  missing = false;
});

function renderBrand(query = "") {
  return render(
    <MemoryRouter initialEntries={[`/brands/${encodeURIComponent(brand.slug)}/${query}`]}>
      <Routes><Route path="/brands/:slug/" element={<BrandPage />} /></Routes>
    </MemoryRouter>
  );
}

describe("brand storefront pages", () => {
  it("reuses the shop grid with a fixed brand scope, breadcrumbs and canonical metadata", async () => {
    const { container } = renderBrand("?brand=another-brand&in_stock=true");
    await screen.findByRole("heading", { name: "محصولات برند یونیک" });
    await screen.findByText("قابلمه ۱");
    const productsHeading = screen.getByRole("heading", { level: 2, name: "محصولات" });
    const productGrid = container.querySelector(".shop .product-grid");
    expect(productsHeading.compareDocumentPosition(productGrid) & 4).toBeTruthy();
    expect(requests.every((params) => params.brand === brand.slug)).toBe(true);
    expect(requests[0].in_stock).toBe("true");
    expect(container.querySelector(".shop .product-grid")).toBeTruthy();
    const crumbs = screen.getByRole("navigation", { name: "مسیر صفحه" });
    expect([...crumbs.querySelectorAll("li")].map((node) => node.textContent)).toEqual(["کازین گالری", "برندها", "یونیک"]);
    expect(document.title).toBe("محصولات برند یونیک | کازین گالری");
    expect(document.querySelector('link[rel="canonical"]').getAttribute("href")).toBe(`https://cusin.ir/brands/${encodeURIComponent(brand.slug)}/`);
    expect(document.querySelector('meta[name="description"]').content).toContain("یونیک");
    const brandOption = screen.getByRole("radio", { name: "یونیک" });
    expect(brandOption.disabled).toBe(true);
    expect(brandOption.checked).toBe(true);
  });

  it("preserves the brand when sorting, filtering or clearing query-string filters", async () => {
    renderBrand("?in_stock=true");
    await screen.findByText("قابلمه ۱");
    fireEvent.change(screen.getByRole("combobox", { name: "مرتب‌سازی:" }), { target: { value: "price_asc" } });
    await waitFor(() => expect(requests.at(-1)).toMatchObject({ brand: brand.slug, ordering: "price_asc" }));
    fireEvent.click(screen.getByRole("button", { name: "حذف همه فیلترها" }));
    await waitFor(() => expect(requests.at(-1).in_stock).toBeUndefined());
    expect(requests.at(-1).brand).toBe(brand.slug);
    fireEvent.click(screen.getByRole("checkbox", { name: "فقط کالاهای موجود" }));
    await waitFor(() => expect(requests.at(-1)).toMatchObject({ brand: brand.slug, in_stock: "true" }));
  });

  it("uses the same mobile load-more behavior as the shop", async () => {
    window.matchMedia = (query) => ({ ...originalMatchMedia(query), matches: query === "(max-width: 767px)" });
    renderBrand();
    await screen.findByText("قابلمه ۱");
    fireEvent.click(screen.getByRole("button", { name: "نمایش کالاهای بیشتر" }));
    await screen.findByText("قابلمه ۲");
    expect(screen.getByText("قابلمه ۱")).toBeTruthy();
    expect(document.querySelector(".product-card--compact .product-card__brand a").getAttribute("href")).toBe(`/brands/${encodeURIComponent(brand.slug)}/`);
    expect(requests.every((params) => params.brand === brand.slug)).toBe(true);
  });

  it("renders a noindex 404 for an unknown or inactive brand instead of an empty shop", async () => {
    missing = true;
    const { container } = renderBrand();
    await screen.findByText("صفحه مورد نظر پیدا نشد؛ شاید نشانی عوض شده است.");
    expect(container.querySelector(".shop")).toBeNull();
    expect(requests.length).toBe(0);
    expect(document.querySelector('meta[name="robots"]').content).toContain("noindex");
  });

  it("links the card brand line to the brand's encoded URL", async () => {
    const { container } = renderBrand();
    await screen.findByText("قابلمه ۱");
    const card = container.querySelector(".product-card");
    expect(within(card).getByRole("link", { name: "یونیک" }).getAttribute("href")).toBe(`/brands/${encodeURIComponent(brand.slug)}/`);
  });
});
