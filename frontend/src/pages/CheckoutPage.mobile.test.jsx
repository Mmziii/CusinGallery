/**
 * Mobile checkout steps (Task 2 redesigned flow):
 * Same 4-step flow on desktop and mobile:
 * 1. Cart (/cart/)
 * 2. Delivery Method (/checkout/?step=delivery)
 * 3. Delivery Info (/checkout/?step=address)
 * 4. Review & Payment (/checkout/?step=review)
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CartPage from "./CartPage";
import CheckoutPage from "./CheckoutPage";
import useCartStore from "../store/useCartStore";

const listAddresses = vi.fn();
const fetchCart = vi.fn();
const fetchShippingMethods = vi.fn();
const placeOrder = vi.fn();
const validateCoupon = vi.fn();
const initiatePayment = vi.fn();
const fetchSiteSettings = vi.fn();
const fetchLocations = vi.fn();

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
vi.mock("../services/couponsApi", () => ({ validateCoupon: (...args) => validateCoupon(...args) }));
vi.mock("../services/paymentsApi", () => ({ initiatePayment: (...args) => initiatePayment(...args) }));
vi.mock("../services/siteApi", () => ({
  fetchSiteSettings: (...args) => fetchSiteSettings(...args),
  fetchLocations: (...args) => fetchLocations(...args),
}));

const CART = {
  items: [
    {
      id: 11,
      quantity: 2,
      line_total: 500000,
      product: { id: 5, name: "قابلمه استیل", slug: "pan" },
      price_info: { price: 250000 },
    },
  ],
  subtotal: 500000,
  total: 500000,
  item_count: 2,
};

const SHIPPING = {
  default: "standard",
  methods: [
    { id: "standard", label: "ارسال عادی", cost: 45000, free_threshold: null, min_days: 3, max_days: 5, requires_address: true },
    { id: "express", label: "ارسال اکسپرس", cost: 90000, free_threshold: null, min_days: 1, max_days: 2, requires_address: true },
    { id: "pickup", label: "دریافت حضوری", cost: 0, free_threshold: null, min_days: 1, max_days: 1, requires_address: false },
  ],
};

const SAVED_ADDRESS = {
  id: 7,
  recipient_name: "سارا احمدی",
  phone: "09121112233",
  province: "تهران",
  city: "تهران",
  address: "خیابان ولیعصر، پلاک ۵",
  postal_code: "1234567890",
  unit: "۳",
  building_number: "۵",
  is_default: true,
};

const originalMatchMedia = window.matchMedia;

function setViewport(mobile) {
  window.matchMedia = (query) => ({
    matches: mobile && query.includes("max-width: 767px"),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

function renderApp(initialEntry = "/checkout/?step=delivery") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/cart/" element={<CartPage />} />
        <Route path="/checkout/" element={<CheckoutPage />} />
      </Routes>
    </MemoryRouter>
  );
}

const bar = () => document.querySelector(".checkout__mobile-bar");
const barButton = () => document.querySelector(".checkout__mobile-bar button");

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  setViewport(true);
  fetchSiteSettings.mockResolvedValue({});
  fetchLocations.mockResolvedValue({ provinces: [] });
  fetchCart.mockResolvedValue(CART);
  listAddresses.mockResolvedValue([SAVED_ADDRESS]);
  fetchShippingMethods.mockResolvedValue(SHIPPING);
  placeOrder.mockResolvedValue({ id: 3, order_number: "CG-3", subtotal: 500000, total: 545000 });
  useCartStore.setState({ cart: CART, isLoading: false, error: null });
});

afterEach(() => {
  cleanup();
  window.matchMedia = originalMatchMedia;
});

describe("mobile checkout steps (Task 2)", () => {
  it("starts at Step 2 (delivery method) on /checkout/ with sticky mobile bar", async () => {
    renderApp("/checkout/?step=delivery");
    await screen.findByRole("heading", { name: /۲\. انتخاب روش تحویل/ });

    expect(bar()).toBeTruthy();
    expect(barButton().textContent).toContain("ادامه: اطلاعات تحویل");
  });

  it("advances from delivery to address to review using the sticky bar button", async () => {
    renderApp("/checkout/?step=delivery");
    await screen.findByRole("heading", { name: /۲\. انتخاب روش تحویل/ });

    // Step 2 -> Step 3
    fireEvent.click(barButton());
    await screen.findByRole("heading", { name: /۳\. اطلاعات تحویل/ });
    expect(barButton().textContent).toContain("ادامه: بازبینی و پرداخت");

    // Step 3 -> Step 4
    fireEvent.click(barButton());
    await screen.findByRole("heading", { name: /۴\. بازبینی و پرداخت/ });
    expect(barButton().textContent).toContain("ثبت سفارش و پرداخت");
  });

  it("renders delivery methods as big selectable cards in Step 2", async () => {
    renderApp("/checkout/?step=delivery");
    await screen.findByRole("heading", { name: /۲\. انتخاب روش تحویل/ });

    const cards = document.querySelectorAll(".shipping-card");
    expect(cards.length).toBe(3);

    // Standard selected by default
    expect(document.querySelector(".shipping-card--active").textContent).toContain("ارسال عادی");

    // Click express
    fireEvent.click(screen.getByRole("radio", { name: /ارسال اکسپرس/ }));
    expect(document.querySelector(".shipping-card--active").textContent).toContain("ارسال اکسپرس");
  });

  it("keeps the payable amount on the sticky bar across every step", async () => {
    renderApp("/checkout/?step=delivery");
    await screen.findByRole("heading", { name: /۲\. انتخاب روش تحویل/ });

    const total = () => bar().querySelector(".checkout__mobile-total").textContent;
    expect(total()).toContain("۵۴۵٬۰۰۰");

    // Change to pickup (free shipping)
    fireEvent.click(screen.getByRole("radio", { name: /دریافت حضوری/ }));
    expect(total()).toContain("۵۰۰٬۰۰۰");

    // Move to step 3
    fireEvent.click(barButton());
    await screen.findByRole("heading", { name: /۳\. اطلاعات تحویل/ });
    expect(total()).toContain("۵۰۰٬۰۰۰");
  });

  it("shows the pickup hours as «۱۰:۰۰ تا ۲۱:۰۰», never as a bare HH:MM-HH:MM", async () => {
    fetchSiteSettings.mockResolvedValue({
      pickup_address: "تهران، میدان تجریش، پلاک ۲۰",
      pickup_hours: "10:00-21:00",
    });
    renderApp("/checkout/?step=delivery");
    await screen.findByRole("heading", { name: /۲\. انتخاب روش تحویل/ });

    fireEvent.click(screen.getByRole("radio", { name: /دریافت حضوری/ }));
    fireEvent.click(barButton());
    await screen.findByRole("heading", { name: /۳\. اطلاعات تحویل/ });

    const info = document.querySelector(".checkout__pickup-info");
    expect(info.textContent).toContain("ساعات تحویل:");
    expect(info.textContent).toContain("۱۰:۰۰ تا ۲۱:۰۰");
    expect(info.textContent).not.toContain("۱۰:۰۰-۲۱:۰۰");
  });

  it("lets completed steps be clicked on the stepper to navigate back", async () => {
    renderApp("/checkout/?step=address");
    await screen.findByRole("heading", { name: /۳\. اطلاعات تحویل/ });

    const stepper = screen.getByRole("list", { name: "مراحل ثبت سفارش" });
    const steps = stepper.querySelectorAll(".checkout__step");

    // Step 1 (cart) and Step 2 (delivery) are done and clickable
    expect(steps[0].classList.contains("checkout__step--clickable")).toBe(true);
    expect(steps[1].classList.contains("checkout__step--clickable")).toBe(true);
    expect(steps[2].classList.contains("checkout__step--current")).toBe(true);

    // Click step 2 link
    const deliveryLink = steps[1].querySelector("a");
    fireEvent.click(deliveryLink);

    await screen.findByRole("heading", { name: /۲\. انتخاب روش تحویل/ });
  });

  it("submits order from review step and redirects to payment", async () => {
    sessionStorage.setItem("cg_checkout_method", "standard");
    sessionStorage.setItem("cg_checkout_addr_id", "7");
    renderApp("/checkout/?step=review");

    await screen.findByRole("heading", { name: /۴\. بازبینی و پرداخت/ });
    fireEvent.click(barButton());

    await waitFor(() => expect(placeOrder).toHaveBeenCalledTimes(1));
    expect(placeOrder.mock.calls[0][0]).toMatchObject({
      address_id: 7,
      shipping_method: "standard",
    });
  });
});
