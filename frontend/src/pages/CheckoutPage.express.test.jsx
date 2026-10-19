import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CheckoutPage from "./CheckoutPage";
import useCartStore from "../store/useCartStore";

const listAddresses = vi.fn();
const fetchCart = vi.fn();
const fetchShippingMethods = vi.fn();
const placeOrder = vi.fn();

vi.mock("../services/authApi", () => ({
  listAddresses: (...args) => listAddresses(...args),
  createAddress: vi.fn(),
  updateAddress: vi.fn(),
}));
vi.mock("../services/cartApi", () => ({ fetchCart: (...args) => fetchCart(...args) }));
vi.mock("../services/orderApi", () => ({
  checkout: (...args) => placeOrder(...args),
  fetchShippingMethods: (...args) => fetchShippingMethods(...args),
}));
vi.mock("../services/couponsApi", () => ({ validateCoupon: vi.fn() }));
vi.mock("../services/paymentsApi", () => ({ initiatePayment: vi.fn() }));
vi.mock("../services/siteApi", () => ({
  fetchSiteSettings: () => Promise.resolve({}),
  fetchLocations: () => Promise.resolve({ provinces: [] }),
}));

const CART = {
  items: [
    {
      id: 11,
      quantity: 1,
      line_total: 250000,
      product: { id: 5, name: "قابلمه استیل", slug: "pan" },
      price_info: { price: 250000 },
    },
  ],
  subtotal: 250000,
  total: 250000,
  item_count: 1,
};
const SHIPPING = {
  default: "standard",
  methods: [
    { id: "standard", label: "ارسال عادی", cost: 45000, free_threshold: null, min_days: 3, max_days: 5, requires_address: true },
    { id: "express", label: "ارسال اکسپرس", cost: 90000, free_threshold: null, min_days: 1, max_days: 1, requires_address: true },
    { id: "pickup", label: "دریافت حضوری", cost: 0, free_threshold: null, min_days: 0, max_days: 0, requires_address: false },
  ],
};
const TEHRAN = {
  id: 7,
  recipient_name: "سارا",
  phone: "09121112233",
  province: "تهران",
  city: "تهران",
  address: "خیابان ولیعصر",
  postal_code: "1234567890",
  unit: "۳",
  building_number: "۵",
  is_default: true,
};
const SHAHRIAR = {
  ...TEHRAN,
  id: 8,
  recipient_name: "مریم",
  city: "شهریار",
  is_default: false,
};

function renderPage(initialEntry = "/checkout/?step=delivery") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/checkout/" element={<CheckoutPage />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  fetchCart.mockResolvedValue(CART);
  fetchShippingMethods.mockResolvedValue(SHIPPING);
  listAddresses.mockResolvedValue([TEHRAN, SHAHRIAR]);
  placeOrder.mockResolvedValue({ id: 1, order_number: "CG-1", subtotal: 250000, total: 340000 });
  useCartStore.setState({ cart: CART, isLoading: false, error: null });
});

afterEach(() => cleanup());

describe("Tehran-city-only express checkout (Task 2)", () => {
  it("shows express card with 'فقط شهر تهران' badge in Step 2", async () => {
    renderPage("/checkout/?step=delivery");
    await screen.findByRole("heading", { name: /۲\. انتخاب روش تحویل/ });

    const expressCard = screen.getByRole("radio", { name: /ارسال اکسپرس/ });
    expect(expressCard).toBeTruthy();
    expect(screen.getByText("فقط شهر تهران")).toBeTruthy();
  });

  it("in Step 3, enables express for Tehran address and disables for other cities with reason", async () => {
    sessionStorage.setItem("cg_checkout_method", "express");
    renderPage("/checkout/?step=address");

    await screen.findByRole("heading", { name: /۳\. اطلاعات تحویل/ });

    const tehranRadio = screen.getByRole("radio", { name: /سارا/ });
    const shahriarRadio = screen.getByRole("radio", { name: /مریم/ });

    expect(tehranRadio.disabled).toBe(false);
    expect(shahriarRadio.disabled).toBe(true);
    expect(screen.getByText("ارسال اکسپرس فقط برای شهر تهران در دسترس است.")).toBeTruthy();
  });

  it("offers to switch to standard delivery when non-Tehran address is selected", async () => {
    sessionStorage.setItem("cg_checkout_method", "express");
    sessionStorage.setItem("cg_checkout_addr_id", "8");
    renderPage("/checkout/?step=address");

    await screen.findByRole("heading", { name: /۳\. اطلاعات تحویل/ });

    expect(screen.getByText(/ارسال اکسپرس برای آن مقدور نمی‌باشد/)).toBeTruthy();
    const switchBtn = screen.getByRole("button", { name: "تغییر به ارسال عادی" });
    expect(switchBtn).toBeTruthy();

    fireEvent.click(switchBtn);
    // Method switches to standard, so Shahriar address becomes selectable
    await waitFor(() => {
      expect(screen.getByRole("radio", { name: /مریم/ }).disabled).toBe(false);
    });
  });

  it("advances to review and places order with express for Tehran destination", async () => {
    sessionStorage.setItem("cg_checkout_method", "express");
    sessionStorage.setItem("cg_checkout_addr_id", "7");
    renderPage("/checkout/?step=review");

    await screen.findByRole("heading", { name: /۴\. بازبینی و پرداخت/ });
    expect(screen.getByText("ارسال اکسپرس")).toBeTruthy();

    const submitBtn = screen.getAllByRole("button", { name: /ثبت سفارش و پرداخت/ })[0];
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(placeOrder).toHaveBeenCalledWith(
        expect.objectContaining({
          address_id: 7,
          shipping_method: "express",
        })
      );
    });
  });
});
