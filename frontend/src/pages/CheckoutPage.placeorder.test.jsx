/**
 * Place-order and validation tests (Task 2 redesigned flow):
 * 1. Cart (/cart/)
 * 2. Delivery Method (/checkout/?step=delivery)
 * 3. Delivery Info (/checkout/?step=address)
 * 4. Review & Payment (/checkout/?step=review)
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CheckoutPage from "./CheckoutPage";
import useCartStore from "../store/useCartStore";

const listAddresses = vi.fn();
const createAddress = vi.fn();
const updateAddress = vi.fn();
const fetchCart = vi.fn();
const fetchShippingMethods = vi.fn();
const placeOrder = vi.fn();
const validateCoupon = vi.fn();
const initiatePayment = vi.fn();
const fetchSiteSettings = vi.fn();
const fetchLocations = vi.fn();

vi.mock("../services/authApi", () => ({
  listAddresses: (...args) => listAddresses(...args),
  createAddress: (...args) => createAddress(...args),
  updateAddress: (...args) => updateAddress(...args),
}));
vi.mock("../services/cartApi", () => ({
  fetchCart: (...args) => fetchCart(...args),
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
    { id: "pickup", label: "دریافت حضوری", cost: 0, free_threshold: null, min_days: 1, max_days: 1, requires_address: false },
  ],
};

const SAVED_ADDRESS = {
  id: 7,
  recipient_name: "سارا",
  phone: "09121112233",
  province: "تهران",
  city: "تهران",
  address: "خیابان ولیعصر، پلاک ۵",
  postal_code: "1234567890",
  unit: "۳",
  building_number: "۵",
  is_default: true,
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
  fetchSiteSettings.mockResolvedValue({});
  fetchLocations.mockResolvedValue({ provinces: [] });
  fetchCart.mockResolvedValue(CART);
  useCartStore.setState({ cart: CART, isLoading: false, error: null });
});

afterEach(() => cleanup());

describe("Place-order button & flow validation (Task 2)", () => {
  it("pickup with no saved address at all: orders with name + phone only", async () => {
    listAddresses.mockResolvedValue([]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    placeOrder.mockResolvedValue({ id: 1, order_number: "CG-1", subtotal: 250000, total: 250000 });

    renderPage("/checkout/?step=delivery");
    await screen.findByRole("heading", { name: "ثبت سفارش" });

    // Choose pickup in step 2
    fireEvent.click(await screen.findByRole("radio", { name: /دریافت حضوری/ }));

    // Proceed to Step 3 (address / pickup info)
    const nextBtn = screen.getAllByRole("button", { name: /ادامه: اطلاعات تحویل/ })[0];
    fireEvent.click(nextBtn);

    await screen.findByRole("heading", { name: /۳\. اطلاعات تحویل/ });
    expect(screen.getByLabelText(/نام تحویل‌گیرنده/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText(/نام تحویل‌گیرنده/), { target: { value: "سارا" } });
    fireEvent.change(screen.getByLabelText(/شماره تماس/), { target: { value: "09121112233" } });

    // Proceed to Step 4 (review)
    const toReviewBtn = screen.getAllByRole("button", { name: /ادامه: بازبینی و پرداخت/ })[0];
    fireEvent.click(toReviewBtn);

    await screen.findByRole("heading", { name: /۴\. بازبینی و پرداخت/ });

    // Submit order
    const submitBtn = screen.getAllByRole("button", { name: /ثبت سفارش و پرداخت/ })[0];
    fireEvent.click(submitBtn);

    await waitFor(() => expect(placeOrder).toHaveBeenCalledTimes(1));
    expect(placeOrder.mock.calls[0][0]).toMatchObject({
      recipient_name: "سارا",
      phone: "09121112233",
      shipping_method: "pickup",
    });
  });

  it("account with zero saved addresses: shows inline form and explains what is missing if empty", async () => {
    listAddresses.mockResolvedValue([]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    sessionStorage.setItem("cg_checkout_method", "standard");

    renderPage("/checkout/?step=address");
    await screen.findByRole("heading", { name: /۳\. اطلاعات تحویل/ });

    const nextBtn = screen.getAllByRole("button", { name: /ادامه: بازبینی و پرداخت/ })[0];
    fireEvent.click(nextBtn);

    // Shows validation error
    expect(await screen.findByText(/آدرس ارسال کامل نیست/)).toBeTruthy();
    expect(placeOrder).not.toHaveBeenCalled();
  });

  it("address list failure offers a retry", async () => {
    listAddresses.mockRejectedValueOnce({ response: { status: 500, data: {} } });
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    sessionStorage.setItem("cg_checkout_method", "standard");

    renderPage("/checkout/?step=address");
    await screen.findByRole("heading", { name: /۳\. اطلاعات تحویل/ });

    expect(await screen.findByRole("button", { name: /تلاش دوباره برای آدرس‌ها/ })).toBeTruthy();

    // Retry succeeds and the saved address is auto-selected
    listAddresses.mockResolvedValue([SAVED_ADDRESS]);
    fireEvent.click(screen.getByRole("button", { name: /تلاش دوباره برای آدرس‌ها/ }));
    await waitFor(() => {
      expect(screen.getByRole("radio", { name: /سارا/ }).checked).toBe(true);
    });
  });

  it("auto-selects the default saved address and the default shipping method on load", async () => {
    listAddresses.mockResolvedValue([SAVED_ADDRESS]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    sessionStorage.setItem("cg_checkout_method", "standard");
    sessionStorage.setItem("cg_checkout_addr_id", "7");
    placeOrder.mockResolvedValue({ id: 2, order_number: "CG-2", subtotal: 250000, total: 295000 });

    renderPage("/checkout/?step=review");
    await screen.findByRole("heading", { name: /۴\. بازبینی و پرداخت/ });

    const submitBtn = screen.getAllByRole("button", { name: /ثبت سفارش و پرداخت/ })[0];
    fireEvent.click(submitBtn);

    await waitFor(() => expect(placeOrder).toHaveBeenCalledTimes(1));
    expect(placeOrder.mock.calls[0][0]).toMatchObject({ address_id: 7, shipping_method: "standard" });
  });

  it("a saved address without plot/unit shows a completion prompt with an edit action", async () => {
    listAddresses.mockResolvedValue([{ ...SAVED_ADDRESS, unit: "", building_number: "" }]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    sessionStorage.setItem("cg_checkout_method", "standard");

    renderPage("/checkout/?step=address");
    await screen.findByRole("heading", { name: /۳\. اطلاعات تحویل/ });

    expect(await screen.findByText(/پلاک و واحد/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /تکمیل این آدرس/ })).toBeTruthy();
  });

  it("a typed but unapplied coupon code is reported before ordering", async () => {
    listAddresses.mockResolvedValue([SAVED_ADDRESS]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    sessionStorage.setItem("cg_checkout_method", "standard");
    sessionStorage.setItem("cg_checkout_addr_id", "7");

    renderPage("/checkout/?step=review");
    await screen.findByRole("heading", { name: /۴\. بازبینی و پرداخت/ });

    fireEvent.change(screen.getByPlaceholderText("کد تخفیف را وارد کنید"), { target: { value: "OFF10" } });

    const submitBtn = screen.getAllByRole("button", { name: /ثبت سفارش و پرداخت/ })[0];
    fireEvent.click(submitBtn);

    expect(placeOrder).not.toHaveBeenCalled();
    expect(await screen.findByText(/کد تخفیف را وارد کرده‌اید اما اعمال نشده است/)).toBeTruthy();
  });

  it("guards against double submit", async () => {
    listAddresses.mockResolvedValue([SAVED_ADDRESS]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    sessionStorage.setItem("cg_checkout_method", "standard");
    sessionStorage.setItem("cg_checkout_addr_id", "7");

    let release;
    placeOrder.mockImplementation(
      () => new Promise((resolve) => { release = () => resolve({ id: 3, order_number: "CG-3", subtotal: 250000, total: 295000 }); })
    );

    renderPage("/checkout/?step=review");
    await screen.findByRole("heading", { name: /۴\. بازبینی و پرداخت/ });

    const submitBtn = screen.getAllByRole("button", { name: /ثبت سفارش و پرداخت/ })[0];
    fireEvent.click(submitBtn);
    fireEvent.click(submitBtn);
    fireEvent.click(submitBtn);

    release();
    await waitFor(() => expect(placeOrder).toHaveBeenCalledTimes(1));
  });

  it("shows a friendly Persian message when the server rate-limits (429)", async () => {
    listAddresses.mockResolvedValue([SAVED_ADDRESS]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    sessionStorage.setItem("cg_checkout_method", "standard");
    sessionStorage.setItem("cg_checkout_addr_id", "7");
    placeOrder.mockRejectedValue({ response: { status: 429, data: {} } });

    renderPage("/checkout/?step=review");
    await screen.findByRole("heading", { name: /۴\. بازبینی و پرداخت/ });

    const submitBtn = screen.getAllByRole("button", { name: /ثبت سفارش و پرداخت/ })[0];
    fireEvent.click(submitBtn);

    expect(await screen.findByText(/تعداد درخواست‌ها در مدت کوتاه زیاد بوده است/)).toBeTruthy();
  });

  it("reports an empty cart instead of proceeding with ordering", async () => {
    listAddresses.mockResolvedValue([SAVED_ADDRESS]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    fetchCart.mockResolvedValue({ items: [], subtotal: 0, total: 0, item_count: 0 });
    useCartStore.setState({ cart: { items: [], subtotal: 0, total: 0, item_count: 0 }, isLoading: false, error: null });

    renderPage("/checkout/?step=delivery");
    expect(await screen.findByText("سبد خرید شما خالی است.")).toBeTruthy();
    expect(placeOrder).not.toHaveBeenCalled();
  });
});
