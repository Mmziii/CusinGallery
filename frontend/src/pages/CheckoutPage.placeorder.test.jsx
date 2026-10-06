/**
 * Part S5 item 4: "دکمهٔ ثبت سفارش غیرفعال است".
 *
 * Reproduces the owner's report first (the button was disabled whenever
 * addressMode === "saved" without a selected address, or "inline" with an
 * empty recipient_name -- which ignores pickup entirely and leaves a
 * shopper with no saved address stuck forever), then locks in the fixed
 * behaviour:
 *   - the button is enabled whenever an order is not being placed;
 *   - clicking it validates everything and shows inline, Persian errors
 *     next to the relevant section (address / shipping / cart / coupon);
 *   - a short "what is still missing" checklist appears under the button;
 *   - pickup needs only a name and a phone, never an address;
 *   - an account with no saved address can still order (inline address);
 *   - an address-list load failure offers a retry instead of a dead end;
 *   - double submits are guarded, and 429/5xx get friendly wording.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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

function renderPage() {
  return render(
    <MemoryRouter>
      <CheckoutPage />
    </MemoryRouter>
  );
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: /ثبت سفارش/ }));
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchSiteSettings.mockResolvedValue({});
  fetchLocations.mockResolvedValue({ provinces: [] });
  fetchCart.mockResolvedValue(CART);
  useCartStore.setState({ cart: null, isLoading: false, error: null });
});

afterEach(() => cleanup());

describe("Place-order button (Part S5 item 4)", () => {
  it("pickup with no saved address at all: button is enabled and orders with name + phone only", async () => {
    listAddresses.mockResolvedValue([]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    placeOrder.mockResolvedValue({ id: 1, order_number: "CG-1", subtotal: 250000, total: 250000 });

    renderPage();
    await screen.findByRole("heading", { name: "ثبت سفارش" });

    // Choose pickup, which needs no postal address.
    fireEvent.click(await screen.findByRole("radio", { name: /دریافت حضوری/ }));

    await waitFor(() => {
      expect(screen.getByLabelText(/نام تحویل‌گیرنده/)).toBeTruthy();
    });
    fireEvent.change(screen.getByLabelText(/نام تحویل‌گیرنده/), { target: { value: "سارا" } });
    fireEvent.change(screen.getByLabelText(/شماره تماس/), { target: { value: "09121112233" } });

    const button = screen.getByRole("button", { name: /ثبت سفارش/ });
    expect(button.disabled).toBe(false);

    submit();
    await waitFor(() => expect(placeOrder).toHaveBeenCalledTimes(1));
    expect(placeOrder.mock.calls[0][0]).toMatchObject({
      recipient_name: "سارا",
      phone: "09121112233",
      shipping_method: "pickup",
    });
  });

  it("account with zero saved addresses: the button is enabled and clicking it explains what is missing inline", async () => {
    listAddresses.mockResolvedValue([]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);

    renderPage();
    await screen.findByRole("heading", { name: "ثبت سفارش" });

    const button = screen.getByRole("button", { name: /ثبت سفارش/ });
    expect(button.disabled).toBe(false);

    submit();

    expect(placeOrder).not.toHaveBeenCalled();
    const errors = await screen.findAllByText(/نام گیرنده را وارد کنید/);
    expect(errors.length).toBeGreaterThan(0);
    // The checklist under the button names what is still missing.
    expect(screen.getByRole("list", { name: "موارد ناقص" })).toBeTruthy();
  });

  it("address list failure offers a retry instead of a permanently dead button", async () => {
    listAddresses.mockRejectedValueOnce({ response: { status: 500, data: {} } });
    fetchShippingMethods.mockResolvedValue(SHIPPING);

    renderPage();
    await screen.findByRole("heading", { name: "ثبت سفارش" });

    expect(await screen.findByRole("button", { name: /تلاش دوباره برای آدرس‌ها/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /ثبت سفارش/ }).disabled).toBe(false);

    // Retry succeeds and the saved address is auto-selected (default first).
    listAddresses.mockResolvedValue([SAVED_ADDRESS]);
    fireEvent.click(screen.getByRole("button", { name: /تلاش دوباره برای آدرس‌ها/ }));
    await waitFor(() => {
      expect(screen.getByRole("radio", { name: /سارا/ }).checked).toBe(true);
    });
  });

  it("auto-selects the default saved address and the default shipping method on load", async () => {
    listAddresses.mockResolvedValue([SAVED_ADDRESS]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    placeOrder.mockResolvedValue({ id: 2, order_number: "CG-2", subtotal: 250000, total: 250000 });

    renderPage();
    await screen.findByRole("heading", { name: "ثبت سفارش" });

    await waitFor(() => expect(screen.getByRole("radio", { name: /سارا/ }).checked).toBe(true));
    expect(screen.getByRole("radio", { name: /ارسال عادی/ }).checked).toBe(true);

    submit();
    await waitFor(() => expect(placeOrder).toHaveBeenCalledTimes(1));
    expect(placeOrder.mock.calls[0][0]).toMatchObject({ address_id: 7, shipping_method: "standard" });
  });

  it("a saved address without plot/unit shows a completion prompt with an edit action, not a silent block", async () => {
    listAddresses.mockResolvedValue([{ ...SAVED_ADDRESS, unit: "", building_number: "" }]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);

    renderPage();
    await screen.findByRole("heading", { name: "ثبت سفارش" });

    expect(await screen.findByText(/پلاک و واحد/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /تکمیل این آدرس/ })).toBeTruthy();
  });

  it("a typed but unapplied coupon code is reported before ordering", async () => {
    listAddresses.mockResolvedValue([SAVED_ADDRESS]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);

    renderPage();
    await screen.findByRole("heading", { name: "ثبت سفارش" });
    fireEvent.change(screen.getByPlaceholderText(/WELCOME10/), { target: { value: "OFF10" } });

    submit();

    expect(placeOrder).not.toHaveBeenCalled();
    expect((await screen.findAllByText(/کد تخفیف.*اعمال نشده/)).length).toBeGreaterThan(0);
  });

  it("guards against double submit", async () => {
    listAddresses.mockResolvedValue([SAVED_ADDRESS]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    let release;
    placeOrder.mockImplementation(
      () => new Promise((resolve) => { release = () => resolve({ id: 3, order_number: "CG-3", subtotal: 250000, total: 250000 }); })
    );

    renderPage();
    await screen.findByRole("heading", { name: "ثبت سفارش" });
    await waitFor(() => expect(screen.getByRole("radio", { name: /سارا/ }).checked).toBe(true));

    submit();
    submit();
    submit();
    release();
    await waitFor(() => expect(screen.getByText(/CG-3/)).toBeTruthy());
    expect(placeOrder).toHaveBeenCalledTimes(1);
  });

  it("shows a friendly Persian message when the server rate-limits (429)", async () => {
    listAddresses.mockResolvedValue([SAVED_ADDRESS]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    placeOrder.mockRejectedValue({ response: { status: 429, data: {} } });

    renderPage();
    await screen.findByRole("heading", { name: "ثبت سفارش" });
    await waitFor(() => expect(screen.getByRole("radio", { name: /سارا/ }).checked).toBe(true));

    submit();
    expect((await screen.findAllByText(/تعداد درخواست‌ها در مدت کوتاه زیاد بوده است/)).length).toBeGreaterThan(0);
    // The button recovers so the shopper can retry.
    await waitFor(() => expect(screen.getByRole("button", { name: /ثبت سفارش/ }).disabled).toBe(false));
  });

  it("reports an empty cart in the checklist instead of a dead button", async () => {
    listAddresses.mockResolvedValue([SAVED_ADDRESS]);
    fetchShippingMethods.mockResolvedValue(SHIPPING);
    fetchCart.mockResolvedValue({ items: [], subtotal: 0, total: 0, item_count: 0 });

    renderPage();
    expect(await screen.findByText("سبد خرید شما خالی است.")).toBeTruthy();
    expect(placeOrder).not.toHaveBeenCalled();
  });
});
