/**
 * Task: the checkout review step showed the receiver's phone in Latin
 * digits («09120000000») while the rest of the page is Persian.
 *
 * Display only: the rendered value is Persianised, while submitted values
 * (payload, validation) stay Latin -- nothing here changes what is sent.
 */
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CheckoutPage from "./CheckoutPage";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";

const listAddresses = vi.fn();
const fetchShippingMethods = vi.fn();
const fetchSiteSettings = vi.fn();
const fetchLocations = vi.fn();
const fetchCartApi = vi.fn();

vi.mock("../services/cartApi", () => ({
  fetchCart: (...args) => fetchCartApi(...args),
}));
vi.mock("../services/authApi", () => ({
  listAddresses: (...args) => listAddresses(...args),
  createAddress: vi.fn(),
  updateAddress: vi.fn(),
}));
vi.mock("../services/orderApi", () => ({
  checkout: vi.fn(),
  fetchShippingMethods: (...args) => fetchShippingMethods(...args),
}));
vi.mock("../services/couponsApi", () => ({
  validateCoupon: vi.fn(),
}));
vi.mock("../services/paymentsApi", () => ({
  initiatePayment: vi.fn(),
}));
vi.mock("../services/siteApi", () => ({
  fetchSiteSettings: (...args) => fetchSiteSettings(...args),
  fetchLocations: (...args) => fetchLocations(...args),
}));

const CART = {
  items: [
    {
      id: 11,
      quantity: 1,
      line_total: 200000,
      product: { id: 5, name: "ست تابه گرانیتی", slug: "pan-set" },
      price_info: { price: 200000 },
    },
  ],
  subtotal: 200000,
  total: 200000,
  item_count: 1,
};

const SHIPPING = {
  default: "standard",
  methods: [
    {
      id: "standard",
      label: "ارسال عادی",
      cost: 50000,
      free_threshold: 1000000,
      min_days: 3,
      max_days: 5,
      requires_address: true,
    },
    {
      id: "pickup",
      label: "دریافت حضوری",
      cost: 0,
      free_threshold: null,
      min_days: 1,
      max_days: 1,
      requires_address: false,
    },
  ],
};

const ADDRESS = {
  id: 7,
  recipient_name: "مریم احمدی",
  phone: "09120000000",
  province: "تهران",
  city: "تهران",
  address: "خیابان ولیعصر",
  postal_code: "1234567890",
  building_number: "۱۰",
  unit: "۲",
  is_default: true,
};

function renderCheckout() {
  return render(
    <MemoryRouter initialEntries={["/checkout/?step=review"]}>
      <Routes>
        <Route path="/checkout/" element={<CheckoutPage />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  fetchCartApi.mockResolvedValue(CART);
  useAuthStore.setState({ isAuthenticated: true, isLoading: false, user: { phone: "09120000000" } });
  useCartStore.setState({ cart: CART, isLoading: false, error: null });
  fetchSiteSettings.mockResolvedValue({
    pickup_address: "تهران، میدان تجریش، پلاک ۲۰",
    pickup_hours: "شنبه تا چهارشنبه ۱۰ تا ۱۹",
  });
  fetchLocations.mockResolvedValue({ provinces: [] });
  fetchShippingMethods.mockResolvedValue(SHIPPING);
  listAddresses.mockResolvedValue([ADDRESS]);
});

afterEach(() => cleanup());

describe("checkout review step phone digits", () => {
  it("shows the saved receiver's phone in Persian digits", async () => {
    sessionStorage.setItem("cg_checkout_method", "standard");
    sessionStorage.setItem("cg_checkout_addr_id", String(ADDRESS.id));
    const { container } = renderCheckout();

    const review = await screen.findByRole("heading", { name: /۴\. بازبینی و پرداخت/ });
    const block = review.closest(".checkout__section");
    await waitFor(() => expect(block.textContent).toContain("۰۹۱۲۰۰۰۰۰۰۰"));
    expect(block.textContent).not.toContain("09120000000");
    // The same block still renders the (already Persianised) postal code.
    expect(block.textContent).toContain("۱۲۳۴۵۶۷۸۹۰");
    expect(container.querySelector(".checkout__review")).toBeTruthy();
  });

  it("shows the pickup contact's phone in Persian digits", async () => {
    sessionStorage.setItem("cg_checkout_method", "pickup");
    sessionStorage.setItem(
      "cg_checkout_pickup",
      JSON.stringify({ recipient_name: "علی رضایی", phone: "09121112233" })
    );
    renderCheckout();

    const review = await screen.findByRole("heading", { name: /۴\. بازبینی و پرداخت/ });
    const block = review.closest(".checkout__section");
    await waitFor(() => expect(block.textContent).toContain("۰۹۱۲۱۱۱۲۲۳۳"));
    expect(block.textContent).not.toContain("09121112233");
    expect(within(block).getByText(/شماره تماس/)).toBeTruthy();
  });
});
