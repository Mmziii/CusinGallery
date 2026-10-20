import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CartPage from "./CartPage";
import CheckoutPage from "./CheckoutPage";
import useCartStore from "../store/useCartStore";
import useAuthStore from "../store/useAuthStore";
import * as behaviour from "../utils/behaviour";

const listAddresses = vi.fn();
const fetchShippingMethods = vi.fn();
const placeOrder = vi.fn();
const validateCoupon = vi.fn();
const initiatePayment = vi.fn();
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
  checkout: (...args) => placeOrder(...args),
  fetchShippingMethods: (...args) => fetchShippingMethods(...args),
}));
vi.mock("../services/couponsApi", () => ({
  validateCoupon: (...args) => validateCoupon(...args),
}));
vi.mock("../services/paymentsApi", () => ({
  initiatePayment: (...args) => initiatePayment(...args),
}));
vi.mock("../services/siteApi", () => ({
  fetchSiteSettings: (...args) => fetchSiteSettings(...args),
  fetchLocations: (...args) => fetchLocations(...args),
}));

const CART = {
  items: [
    {
      id: 11,
      quantity: 2,
      line_total: 200000,
      product: { id: 5, name: "ست تابه گرانیتی", slug: "pan-set" },
      price_info: { price: 100000 },
    },
  ],
  subtotal: 200000,
  total: 200000,
  item_count: 2,
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
      description: "تحویل با پست پیشتاز",
    },
    {
      id: "express",
      label: "ارسال اکسپرس",
      cost: 90000,
      free_threshold: null,
      min_days: 1,
      max_days: 1,
      requires_address: true,
      description: "تحویل فوری",
    },
    {
      id: "pickup",
      label: "دریافت حضوری",
      cost: 0,
      free_threshold: null,
      min_days: 1,
      max_days: 1,
      requires_address: false,
      description: "تحویل در فروشگاه",
    },
  ],
};

const TEHRAN_ADDRESS = {
  id: 1,
  recipient_name: "مریم احمدی",
  phone: "09123456789",
  province: "تهران",
  city: "تهران",
  address: "خیابان ولیعصر",
  postal_code: "1234567890",
  building_number: "۱۰",
  unit: "۲",
  is_default: true,
};

const ISFAHAN_ADDRESS = {
  id: 2,
  recipient_name: "علی رضایی",
  phone: "09131112233",
  province: "اصفهان",
  city: "اصفهان",
  address: "خیابان چهارباغ",
  postal_code: "9876543210",
  building_number: "۱۲",
  unit: "۱",
  is_default: false,
};

function renderCheckout(initialEntry = "/checkout/?step=delivery") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/cart/" element={<CartPage />} />
        <Route path="/checkout/" element={<CheckoutPage />} />
      </Routes>
    </MemoryRouter>
  );
}

/** Renders the app plus a probe of the live URL, so a redirect can be
 *  asserted (MemoryRouter never touches window.location). */
function renderWithLocationProbe(initialEntry = "/checkout/") {
  function LocationProbe() {
    const location = useLocation();
    return (
      <output data-testid="location" hidden>
        {`${location.pathname}${location.search}`}
      </output>
    );
  }
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/cart/" element={<CartPage />} />
        <Route path="/checkout/" element={<CheckoutPage />} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>
  );
}

const currentUrl = () => screen.getByTestId("location").textContent;

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  fetchCartApi.mockResolvedValue(CART);
  useAuthStore.setState({ isAuthenticated: true, isLoading: false, user: { phone: "09123456789" } });
  useCartStore.setState({ cart: CART, isLoading: false, error: null });
  fetchSiteSettings.mockResolvedValue({
    pickup_address: "تهران، میدان تجریش، پلاک ۲۰",
    pickup_hours: "شنبه تا چهارشنبه ۱۰ تا ۱۹",
  });
  fetchLocations.mockResolvedValue({ provinces: [] });
  fetchShippingMethods.mockResolvedValue(SHIPPING);
  listAddresses.mockResolvedValue([TEHRAN_ADDRESS, ISFAHAN_ADDRESS]);
  placeOrder.mockResolvedValue({ id: 101, order_number: "CG-101", total: 250000 });
  initiatePayment.mockResolvedValue({ redirect_url: "https://zarinpal.com/gateway/mock" });
});

afterEach(() => cleanup());

describe("Redesigned Checkout Flow (Task 2)", () => {
  it("renders the 4-step stepper on /cart/ with step 1 current", async () => {
    render(
      <MemoryRouter initialEntries={["/cart/"]}>
        <Routes>
          <Route path="/cart/" element={<CartPage />} />
        </Routes>
      </MemoryRouter>
    );

    const stepper = await screen.findByRole("list", { name: "مراحل ثبت سفارش" });
    const steps = stepper.querySelectorAll(".checkout__step");
    expect(steps).toHaveLength(4);

    expect(steps[0].classList.contains("checkout__step--current")).toBe(true);
    expect(steps[0].getAttribute("aria-current")).toBe("step");
    expect(steps[1].classList.contains("checkout__step--todo")).toBe(true);
    expect(steps[2].classList.contains("checkout__step--todo")).toBe(true);
    expect(steps[3].classList.contains("checkout__step--todo")).toBe(true);
  });

  it("fires checkout_started analytics event upon entering step 2 (delivery)", async () => {
    const trackSpy = vi.spyOn(behaviour, "trackEvent");
    renderCheckout("/checkout/?step=delivery");

    await screen.findByRole("heading", { name: /۲\. انتخاب روش تحویل/ });
    expect(trackSpy).toHaveBeenCalledWith("checkout_started");
  });

  it("Step 2 displays big cards with express Tehran-only badge, and updates invoice summary on selection", async () => {
    renderCheckout("/checkout/?step=delivery");

    await screen.findByRole("heading", { name: /۲\. انتخاب روش تحویل/ });

    // Big cards rendered
    expect(screen.getByText("ارسال عادی")).toBeTruthy();
    expect(screen.getByText("ارسال اکسپرس")).toBeTruthy();
    expect(screen.getByText("دریافت حضوری")).toBeTruthy();
    expect(screen.getByText("فقط شهر تهران")).toBeTruthy();

    // Default is standard (cost 50,000) -> total 250,000
    const summary = document.querySelector(".checkout__summary");
    expect(summary.textContent).toContain("۵۰٬۰۰۰");
    expect(summary.textContent).toContain("۲۵۰٬۰۰۰");

    // Click express -> shipping cost becomes 90,000 -> total 290,000
    const expressCard = screen.getByRole("radio", { name: /ارسال اکسپرس/ });
    fireEvent.click(expressCard);

    expect(summary.textContent).toContain("۹۰٬۰۰۰");
    expect(summary.textContent).toContain("۲۹۰٬۰۰۰");

    // Click pickup -> shipping becomes free -> total 200,000
    const pickupCard = screen.getByRole("radio", { name: /دریافت حضوری/ });
    fireEvent.click(pickupCard);

    expect(summary.textContent).toContain("رایگان");
    expect(summary.textContent).toContain("۲۰۰٬۰۰۰");
  });

  it("URL guard redirects from review to address if address/contact is not ready", async () => {
    // Zero addresses and no pickup contact set
    listAddresses.mockResolvedValue([]);
    renderCheckout("/checkout/?step=review");

    // Must be redirected to delivery or address
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: /۴\. بازبینی و پرداخت/ })).toBeNull();
    });
  });

  it("Step 3 for pickup shows pickup address/hours and asks only for receiver name and phone", async () => {
    sessionStorage.setItem("cg_checkout_method", "pickup");
    renderCheckout("/checkout/?step=address");

    await screen.findByRole("heading", { name: /۳\. اطلاعات تحویل/ });

    // Store address and hours shown
    expect(screen.getByText(/میدان تجریش/)).toBeTruthy();
    expect(screen.getByText(/شنبه تا چهارشنبه/)).toBeTruthy();

    // Only recipient name and mobile are asked
    expect(screen.getByLabelText(/نام تحویل‌گیرنده/)).toBeTruthy();
    expect(screen.getByLabelText(/شماره تماس/)).toBeTruthy();

    // Postal address fields should not exist
    expect(screen.queryByLabelText(/کد پستی/)).toBeNull();
    expect(screen.queryByLabelText(/آدرس کامل/)).toBeNull();
  });

  it("Step 3 for express disables non-Tehran addresses and allows Tehran addresses", async () => {
    sessionStorage.setItem("cg_checkout_method", "express");
    renderCheckout("/checkout/?step=address");

    await screen.findByRole("heading", { name: /۳\. اطلاعات تحویل/ });

    // Tehran address should be selectable
    const tehranRadio = screen.getByRole("radio", { name: /مریم احمدی/ });
    expect(tehranRadio.disabled).toBe(false);

    // Isfahan address should be disabled with warning
    const isfahanRadio = screen.getByRole("radio", { name: /علی رضایی/ });
    expect(isfahanRadio.disabled).toBe(true);
    expect(screen.getByText("ارسال اکسپرس فقط برای شهر تهران در دسترس است.")).toBeTruthy();
  });

  it("Step 4 allows navigation back to earlier steps with «تغییر» buttons and submits order", async () => {
    sessionStorage.setItem("cg_checkout_method", "standard");
    sessionStorage.setItem("cg_checkout_addr_id", "1");
    renderCheckout("/checkout/?step=review");

    await screen.findByRole("heading", { name: /۴\. بازبینی و پرداخت/ });

    // Items, method, address review blocks present
    expect(screen.getByText(/ست تابه گرانیتی/)).toBeTruthy();
    expect(screen.getByText("روش تحویل انتخاب‌شده")).toBeTruthy();
    expect(screen.getByText("آدرس تحویل")).toBeTruthy();

    // «تغییر» buttons
    const changeButtons = screen.getAllByRole("button", { name: "تغییر" });
    expect(changeButtons.length).toBeGreaterThanOrEqual(2);

    // Submit order button
    const submitBtn = screen.getAllByRole("button", { name: /ثبت سفارش و پرداخت/ })[0];
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(placeOrder).toHaveBeenCalledTimes(1);
    });
    expect(placeOrder).toHaveBeenCalledWith(
      expect.objectContaining({
        address_id: 1,
        shipping_method: "standard",
      })
    );
  });
});

describe("no single-page checkout (the cart's step must never be skipped)", () => {
  it("replaces /checkout/ (no step) with ?step=delivery", async () => {
    listAddresses.mockResolvedValue([TEHRAN_ADDRESS]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    renderWithLocationProbe("/checkout/");

    await screen.findByRole("heading", { name: /۲\. انتخاب روش تحویل/ });
    expect(currentUrl()).toBe("/checkout/?step=delivery");
  });

  it("replaces an unknown step with ?step=delivery", async () => {
    listAddresses.mockResolvedValue([TEHRAN_ADDRESS]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    renderWithLocationProbe("/checkout/?step=pay-now");

    await screen.findByRole("heading", { name: /۲\. انتخاب روش تحویل/ });
    expect(currentUrl()).toBe("/checkout/?step=delivery");
  });

  it("the cart's «ادامه و ثبت سفارش» links to the first step", async () => {
    render(
      <MemoryRouter initialEntries={["/cart/"]}>
        <Routes>
          <Route path="/cart/" element={<CartPage />} />
        </Routes>
      </MemoryRouter>
    );

    const cartButton = await screen.findByRole("link", { name: "ادامه و ثبت سفارش" });
    expect(cartButton.getAttribute("href")).toBe("/checkout/?step=delivery");

    const mobileButton = document.querySelector(".cart-page__mobile-bar a");
    expect(mobileButton).toBeTruthy();
    expect(mobileButton.getAttribute("href")).toBe("/checkout/?step=delivery");
  });

  it("never places an order from the delivery or the address step", async () => {
    listAddresses.mockResolvedValue([TEHRAN_ADDRESS]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);

    // Step 2 (delivery): the only action moves the flow forward.
    renderCheckout("/checkout/?step=delivery");
    await screen.findByRole("heading", { name: /۲\. انتخاب روش تحویل/ });
    fireEvent.click(screen.getAllByRole("button", { name: /ادامه: اطلاعات تحویل/ })[0]);
    await screen.findByRole("heading", { name: /۳\. اطلاعات تحویل/ });
    expect(placeOrder).not.toHaveBeenCalled();

    // Step 3 (address): same -- there is no «ثبت سفارش» button here at all.
    expect(screen.queryByRole("button", { name: /ثبت سفارش/ })).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: /ادامه: بازبینی و پرداخت/ })[0]);
    await screen.findByRole("heading", { name: /۴\. بازبینی و پرداخت/ });
    expect(placeOrder).not.toHaveBeenCalled();

    // Only the review step can place the order.
    fireEvent.click(screen.getAllByRole("button", { name: /ثبت سفارش و پرداخت/ })[0]);
    await waitFor(() => expect(placeOrder).toHaveBeenCalledTimes(1));
  });

  it("shows the coupon field only on the review step", async () => {
    listAddresses.mockResolvedValue([TEHRAN_ADDRESS]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);

    renderCheckout("/checkout/?step=delivery");
    await screen.findByRole("heading", { name: /۲\. انتخاب روش تحویل/ });
    expect(document.getElementById("checkout-coupon")).toBeNull();

    fireEvent.click(screen.getAllByRole("button", { name: /ادامه: اطلاعات تحویل/ })[0]);
    await screen.findByRole("heading", { name: /۳\. اطلاعات تحویل/ });
    expect(document.getElementById("checkout-coupon")).toBeNull();

    fireEvent.click(screen.getAllByRole("button", { name: /ادامه: بازبینی و پرداخت/ })[0]);
    await screen.findByRole("heading", { name: /۴\. بازبینی و پرداخت/ });
    expect(document.getElementById("checkout-coupon")).toBeTruthy();
  });
});
