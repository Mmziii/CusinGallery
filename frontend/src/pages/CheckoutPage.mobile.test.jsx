/**
 * Audit 19 item 2: the checkout on a phone.
 *
 * The owner's report: «روش ارسال» sat far below the address list where
 * nobody scrolled, so nobody noticed the delivery choice. On a phone the
 * checkout is now a real step-by-step flow driven by the existing stepper:
 *
 *   step 0 address   -> «ادامه: انتخاب روش ارسال»
 *   step 1 delivery  -> «ادامه: بازبینی»
 *   step 2 review    -> «ثبت سفارش»
 *
 * ONE step is visible at a time, the sticky bottom bar always carries the
 * current step's main button plus the payable amount, earlier steps are
 * clickable to go back, and a step cannot be left while its own validation
 * fails (the cart and the order are untouched by a failed check).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

function renderPage() {
  return render(
    <MemoryRouter>
      <CheckoutPage />
    </MemoryRouter>
  );
}

const step = (id) => document.getElementById(id);
const bar = () => document.querySelector(".checkout__mobile-bar");
const barButton = () => screen.getByRole("button", { name: /ادامه|ثبت سفارش/ });

/** The address step is ready once the saved address finished loading. */
async function readyAtAddressStep() {
  renderPage();
  await screen.findByRole("heading", { name: "ثبت سفارش" });
  await waitFor(() => expect(document.querySelectorAll(".address-card").length).toBe(1));
}

beforeEach(() => {
  vi.clearAllMocks();
  setViewport(true);
  fetchSiteSettings.mockResolvedValue({});
  fetchLocations.mockResolvedValue({ provinces: [] });
  fetchCart.mockResolvedValue(CART);
  listAddresses.mockResolvedValue([SAVED_ADDRESS]);
  fetchShippingMethods.mockResolvedValue(SHIPPING);
  placeOrder.mockResolvedValue({ id: 3, order_number: "CG-3", subtotal: 500000, total: 545000 });
  useCartStore.setState({ cart: null, isLoading: false, error: null });
});

afterEach(() => {
  cleanup();
  window.matchMedia = originalMatchMedia;
});

describe("mobile checkout steps", () => {
  it("shows ONE step at a time, starting with the address", async () => {
    await readyAtAddressStep();

    expect(step("checkout-section-address").hidden).toBe(false);
    expect(step("checkout-section-shipping").hidden).toBe(true);
    expect(step("checkout-section-review").hidden).toBe(true);
    // The desktop summary is replaced by the review step on a phone.
    expect(step("checkout-section-cart").hidden).toBe(true);
    expect(bar()).toBeTruthy();
    expect(barButton().textContent).toBe("ادامه: انتخاب روش ارسال");
  });

  it("walks address -> delivery -> review with the sticky bar's button", async () => {
    await readyAtAddressStep();

    fireEvent.click(barButton());
    // Delivery is now the one visible step, and its heading is explicit.
    await waitFor(() => expect(step("checkout-section-shipping").hidden).toBe(false));
    expect(step("checkout-section-address").hidden).toBe(true);
    expect(screen.getByRole("heading", { name: "روش ارسال" })).toBeTruthy();
    expect(barButton().textContent).toBe("ادامه: بازبینی");

    fireEvent.click(barButton());
    await waitFor(() => expect(step("checkout-section-review").hidden).toBe(false));
    expect(step("checkout-section-shipping").hidden).toBe(true);
    expect(barButton().textContent).toBe("ثبت سفارش");
  });

  it("renders the delivery methods as selectable cards with the selected one highlighted", async () => {
    await readyAtAddressStep();
    fireEvent.click(barButton());
    await waitFor(() => expect(step("checkout-section-shipping").hidden).toBe(false));

    // Three big cards: icon + title + delivery window + price.
    const cards = document.querySelectorAll(".shipping-method");
    expect(cards.length).toBe(3);
    for (const card of cards) {
      expect(card.querySelector(".shipping-method__icon")).toBeTruthy();
      expect(card.querySelector(".shipping-method__cost")).toBeTruthy();
      expect(card.querySelector(".shipping-method__body")).toBeTruthy();
    }
    // Pickup is free and says so.
    const pickup = screen.getByRole("radio", { name: /دریافت حضوری/ }).closest(".shipping-method");
    expect(pickup.querySelector(".shipping-method__cost").textContent).toBe("رایگان");
    expect(screen.getByRole("radio", { name: /ارسال عادی/ }).checked).toBe(true);
    expect(screen.getByRole("radio", { name: /ارسال عادی/ }).closest(".shipping-method").className).toContain(
      "shipping-method--active"
    );

    // Choosing another card moves the highlight.
    fireEvent.click(screen.getByRole("radio", { name: /ارسال اکسپرس/ }));
    expect(screen.getByRole("radio", { name: /ارسال اکسپرس/ }).closest(".shipping-method").className).toContain(
      "shipping-method--active"
    );
    expect(document.querySelectorAll(".shipping-method--active").length).toBe(1);
  });

  it("summarises address, delivery method (with «تغییر») and the items on the review step", async () => {
    await readyAtAddressStep();
    fireEvent.click(barButton());
    await waitFor(() => expect(step("checkout-section-shipping").hidden).toBe(false));
    fireEvent.click(barButton());
    await waitFor(() => expect(step("checkout-section-review").hidden).toBe(false));

    const review = step("checkout-section-review");
    expect(review.textContent).toContain("سارا احمدی");
    expect(review.textContent).toContain("ولیعصر");
    expect(review.textContent).toContain("ارسال عادی");
    expect(review.textContent).toContain("قابلمه استیل");
    expect(review.textContent).toContain("۴۵٬۰۰۰");
    // The coupon input stays reachable (the owner explicitly asked not to
    // break it) -- it sits with the review step on a phone.
    expect(step("checkout-section-coupon").hidden).toBe(false);
    expect(screen.getByLabelText("کد تخفیف")).toBeTruthy();

    // «تغییر» on the delivery block goes back to that step.
    const changeButtons = [...review.querySelectorAll(".checkout__review-change")];
    expect(changeButtons.length).toBeGreaterThanOrEqual(2);
    fireEvent.click(changeButtons[1]);
    await waitFor(() => expect(step("checkout-section-shipping").hidden).toBe(false));
    expect(step("checkout-section-review").hidden).toBe(true);
  });

  it("lets earlier steps be tapped on the stepper to go back", async () => {
    await readyAtAddressStep();
    fireEvent.click(barButton());
    await waitFor(() => expect(step("checkout-section-shipping").hidden).toBe(false));

    // The stepper's earlier step is a real button now.
    const stepper = screen.getByRole("list", { name: "مراحل ثبت سفارش" });
    const addressStep = [...stepper.querySelectorAll("li")][0];
    const backButton = addressStep.querySelector("button");
    expect(backButton).toBeTruthy();
    expect(addressStep.getAttribute("aria-current")).toBeNull();
    expect([...stepper.querySelectorAll("li")][1].getAttribute("aria-current")).toBe("step");

    fireEvent.click(backButton);
    await waitFor(() => expect(step("checkout-section-address").hidden).toBe(false));
    expect(step("checkout-section-shipping").hidden).toBe(true);
  });

  it("keeps the payable amount on the sticky bar at every step", async () => {
    await readyAtAddressStep();
    const total = () => bar().querySelector(".checkout__mobile-total").textContent;
    // 500,000 goods + 45,000 standard shipping.
    expect(total()).toContain("۵۴۵٬۰۰۰");

    fireEvent.click(barButton());
    await waitFor(() => expect(step("checkout-section-shipping").hidden).toBe(false));
    fireEvent.click(screen.getByRole("radio", { name: /دریافت حضوری/ }));
    expect(total()).toContain("۵۰۰٬۰۰۰");
  });

  it("does not leave a step whose own validation fails, and never touches the cart", async () => {
    // An account with no saved address: the inline form opens, empty.
    listAddresses.mockResolvedValue([]);
    renderPage();
    await screen.findByRole("heading", { name: "ثبت سفارش" });
    await waitFor(() => expect(screen.getByLabelText(/نام گیرنده/)).toBeTruthy());

    fireEvent.click(barButton());

    // The same Persian message shows next to the fields AND on the sticky
    // bar, where the shopper just tapped.
    await waitFor(() =>
      expect(screen.getAllByText(/آدرس ارسال کامل نیست|یک آدرس ذخیره‌شده انتخاب کنید/).length).toBeGreaterThan(0)
    );
    expect(step("checkout-section-shipping").hidden).toBe(true);
    expect(bar().querySelector(".checkout__issue")).toBeTruthy();
    expect(placeOrder).not.toHaveBeenCalled();
  });

  it("places the order from the review step and keeps the coupon working", async () => {
    await readyAtAddressStep();
    validateCoupon.mockResolvedValue({ code: "OFF10", discount_amount: 50000 });
    fireEvent.click(barButton());
    await waitFor(() => expect(step("checkout-section-shipping").hidden).toBe(false));
    fireEvent.click(barButton());
    await waitFor(() => expect(step("checkout-section-review").hidden).toBe(false));

    fireEvent.change(screen.getByLabelText("کد تخفیف"), { target: { value: "OFF10" } });
    fireEvent.click(screen.getByRole("button", { name: "اعمال" }));
    await waitFor(() => expect(validateCoupon).toHaveBeenCalledWith("OFF10"));
    await waitFor(() => expect(step("checkout-section-review").textContent).toContain("۵۰۰٬۰۰۰"));

    fireEvent.click(barButton());
    await waitFor(() => expect(placeOrder).toHaveBeenCalledTimes(1));
    expect(placeOrder.mock.calls[0][0]).toMatchObject({
      address_id: 7,
      shipping_method: "standard",
      coupon_code: "OFF10",
    });
    expect(await screen.findByText(/سفارش شما ثبت شد/)).toBeTruthy();
  });

  it("keeps the desktop checkout as the single-page layout", async () => {
    setViewport(false);
    renderPage();
    await screen.findByRole("heading", { name: "ثبت سفارش" });
    await waitFor(() => expect(document.querySelectorAll(".address-card").length).toBe(1));

    // Nothing is gated and the classic summary with the submit button exists.
    expect(step("checkout-section-address").hidden).toBe(false);
    expect(step("checkout-section-shipping").hidden).toBe(false);
    expect(step("checkout-section-cart").hidden).toBe(false);
    expect(bar()).toBeNull();
    expect(screen.getByRole("button", { name: "ثبت سفارش" })).toBeTruthy();
    // The delivery section comes directly after the address in the DOM.
    const sections = [...document.querySelectorAll(".checkout__main > .checkout__section")].map((el) => el.id);
    expect(sections.slice(0, 2)).toEqual(["checkout-section-address", "checkout-section-shipping"]);
  });
});
