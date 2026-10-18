import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CheckoutPage from "./CheckoutPage";
import useCartStore from "../store/useCartStore";

const listAddresses = vi.fn();
const fetchCart = vi.fn();
const fetchShippingMethods = vi.fn();
const placeOrder = vi.fn();

vi.mock("../services/authApi", () => ({ listAddresses: (...args) => listAddresses(...args), createAddress: vi.fn(), updateAddress: vi.fn() }));
vi.mock("../services/cartApi", () => ({ fetchCart: (...args) => fetchCart(...args) }));
vi.mock("../services/orderApi", () => ({ checkout: (...args) => placeOrder(...args), fetchShippingMethods: (...args) => fetchShippingMethods(...args) }));
vi.mock("../services/couponsApi", () => ({ validateCoupon: vi.fn() }));
vi.mock("../services/paymentsApi", () => ({ initiatePayment: vi.fn() }));
vi.mock("../services/siteApi", () => ({ fetchSiteSettings: () => Promise.resolve({}), fetchLocations: () => Promise.resolve({ provinces: [] }) }));

const CART = {
  items: [{ id: 11, quantity: 1, line_total: 250000, product: { id: 5, name: "قابلمه استیل", slug: "pan" }, price_info: { price: 250000 } }],
  subtotal: 250000, total: 250000, item_count: 1,
};
const SHIPPING = {
  default: "standard",
  methods: [
    { id: "standard", label: "ارسال عادی", cost: 45000, free_threshold: null, min_days: 3, max_days: 5, requires_address: true },
    { id: "express", label: "ارسال اکسپرس", cost: 90000, free_threshold: null, min_days: 1, max_days: 1, requires_address: true },
    { id: "pickup", label: "دریافت حضوری", cost: 0, free_threshold: null, min_days: 0, max_days: 0, requires_address: false },
  ],
};
const TEHRAN = { id: 7, recipient_name: "سارا", phone: "09121112233", province: "تهران", city: "تهران", address: "خیابان ولیعصر", postal_code: "1234567890", unit: "۳", building_number: "۵", is_default: true };
const SHAHRIAR = { ...TEHRAN, id: 8, recipient_name: "مریم", city: "شهریار", is_default: false };
const originalMatchMedia = window.matchMedia;
const express = () => screen.getByRole("radio", { name: /ارسال اکسپرس/ });
const standard = () => screen.getByRole("radio", { name: /ارسال عادی/ });
const renderPage = () => render(<MemoryRouter><CheckoutPage /></MemoryRouter>);
const ready = async () => {
  renderPage();
  await screen.findByRole("heading", { name: "ثبت سفارش" });
  await waitFor(() => expect(document.querySelectorAll(".address-card").length).toBeGreaterThan(0));
};

beforeEach(() => {
  vi.clearAllMocks();
  fetchCart.mockResolvedValue(CART);
  fetchShippingMethods.mockResolvedValue(SHIPPING);
  listAddresses.mockResolvedValue([TEHRAN, SHAHRIAR]);
  placeOrder.mockResolvedValue({ id: 1, order_number: "CG-1", subtotal: 250000, total: 295000 });
  useCartStore.setState({ cart: null, isLoading: false, error: null });
});
afterEach(() => { cleanup(); window.matchMedia = originalMatchMedia; });

describe("Tehran-city-only express checkout", () => {
  it("enables express for the selected Tehran-city address", async () => {
    await ready();
    expect(express().disabled).toBe(false);
    fireEvent.click(express());
    expect(express().checked).toBe(true);
    expect(screen.queryByText("ارسال اکسپرس فعلاً فقط برای شهر تهران")).toBeNull();
  });

  it("disables express for other cities in the same province and explains why", async () => {
    listAddresses.mockResolvedValue([{ ...SHAHRIAR, is_default: true }]);
    await ready();
    expect(express().disabled).toBe(true);
    expect(standard().checked).toBe(true);
    expect(screen.getByText("ارسال اکسپرس فعلاً فقط برای شهر تهران")).toBeTruthy();
    expect(express().getAttribute("aria-describedby")).toBe("checkout-express-note");
    expect(screen.getByRole("radio", { name: /دریافت حضوری/ }).disabled).toBe(false);
  });

  it("falls back immediately after a saved address change, updates totals and submits normal delivery", async () => {
    await ready();
    fireEvent.click(express());
    expect(document.querySelector(".checkout__summary").textContent).toContain("۳۴۰٬۰۰۰");
    fireEvent.click(screen.getByRole("radio", { name: /مریم/ }));
    expect(express().disabled).toBe(true);
    expect(express().checked).toBe(false);
    expect(standard().checked).toBe(true);
    expect(document.querySelector(".checkout__summary").textContent).toContain("۲۹۵٬۰۰۰");
    fireEvent.click(screen.getByRole("button", { name: "ثبت سفارش" }));
    await waitFor(() => expect(placeOrder).toHaveBeenCalledExactlyOnceWith({ address_id: 8, shipping_method: "standard" }));
  });

  it("rechecks the one-off address and both city and province changes", async () => {
    await ready();
    fireEvent.click(express());
    fireEvent.click(screen.getByRole("radio", { name: /یک‌بار مصرف/ }));
    expect(express().disabled).toBe(true);
    expect(standard().checked).toBe(true);
    fireEvent.change(screen.getByLabelText(/استان/), { target: { value: "تهران" } });
    fireEvent.change(screen.getByLabelText(/^شهر/), { target: { value: "تهران" } });
    expect(express().disabled).toBe(false);
    fireEvent.click(express());
    fireEvent.change(screen.getByLabelText(/^شهر/), { target: { value: "پردیس" } });
    expect(express().disabled).toBe(true);
    expect(standard().checked).toBe(true);
    fireEvent.change(screen.getByLabelText(/^شهر/), { target: { value: "تهران" } });
    fireEvent.click(express());
    fireEvent.change(screen.getByLabelText(/استان/), { target: { value: "البرز" } });
    expect(express().disabled).toBe(true);
    expect(standard().checked).toBe(true);
  });

  it("keeps pickup unchanged regardless of a non-Tehran destination", async () => {
    listAddresses.mockResolvedValue([SHAHRIAR]);
    await ready();
    const pickup = screen.getByRole("radio", { name: /دریافت حضوری/ });
    fireEvent.click(pickup);
    expect(pickup.checked).toBe(true);
    expect(screen.getByLabelText(/نام تحویل‌گیرنده/)).toBeTruthy();
    expect(express().disabled).toBe(true);
  });

  it("applies the same fallback when a phone shopper goes back to choose a different address", async () => {
    window.matchMedia = (query) => ({ matches: query === "(max-width: 767px)", media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() });
    await ready();
    const next = () => document.querySelector(".checkout__mobile-bar .btn");
    fireEvent.click(next());
    expect(express().disabled).toBe(false);
    fireEvent.click(express());
    const steps = screen.getByRole("list", { name: "مراحل ثبت سفارش" });
    fireEvent.click(steps.querySelector("li button"));
    fireEvent.click(screen.getByRole("radio", { name: /مریم/ }));
    fireEvent.click(next());
    expect(express().disabled).toBe(true);
    expect(standard().checked).toBe(true);
  });
});
