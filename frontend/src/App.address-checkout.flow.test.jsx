/*
 * Regression for the real customer path that exposed the address-envelope
 * crash: services talk to an HTTP-shaped, CSRF-checking adapter (not mocked
 * service functions), so GET /accounts/addresses/ has the same paginated
 * response shape as Django REST Framework.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import App from "./App";
import apiClient from "./services/apiClient";
import useAuthStore from "./store/useAuthStore";
import useCartStore from "./store/useCartStore";

const originalAdapter = apiClient.defaults.adapter;

const CUSTOMER = { id: 41, phone: "09121112233", first_name: "سارا", last_name: "احمدی" };
const CART = {
  item_count: 1,
  subtotal: 250000,
  total: 250000,
  items: [
    {
      id: 101,
      quantity: 1,
      line_total: 250000,
      product: { id: 5, name: "قابلمه استیل", slug: "pan", primary_image: null },
      price_info: { price: 250000 },
    },
  ],
};
const SHIPPING = {
  default: "standard",
  methods: [
    { id: "standard", label: "ارسال عادی", cost: 45000, free_threshold: null, min_days: 3, max_days: 5, requires_address: true },
    { id: "pickup", label: "دریافت حضوری", cost: 0, free_threshold: null, min_days: 1, max_days: 1, requires_address: false },
  ],
};

const ok = (data, config) => ({ data, status: 200, statusText: "OK", headers: {}, config });
const page = (results) => ({ count: results.length, next: null, previous: null, results });

function fillNewAddress() {
  fireEvent.change(screen.getByLabelText(/^نام گیرنده/), { target: { value: "سارا احمدی" } });
  fireEvent.change(screen.getByLabelText(/^شماره تماس/), { target: { value: "09121112233" } });
  fireEvent.change(screen.getByLabelText(/^استان/), { target: { value: "تهران" } });
  fireEvent.change(screen.getByLabelText(/^شهر/), { target: { value: "تهران" } });
  fireEvent.change(screen.getByLabelText(/^آدرس کامل/), { target: { value: "ولیعصر، پلاک ۵" } });
  fireEvent.change(screen.getByLabelText(/^کد پستی/), { target: { value: "1234567890" } });
  fireEvent.change(screen.getByLabelText(/^پلاک/), { target: { value: "5" } });
  fireEvent.change(screen.getByLabelText(/^واحد/), { target: { value: "3" } });
}

async function addAddressThenOpenCheckout() {
  await screen.findByRole("heading", { name: "آدرس‌های من" });
  fireEvent.click(screen.getByRole("button", { name: /آدرس جدید/ }));
  fillNewAddress();
  fireEvent.click(screen.getByRole("button", { name: "افزودن آدرس" }));

  // The page re-fetches after creation. Seeing this card proves that the
  // paginated server response was normalized back to a renderable array.
  await screen.findByText("سارا احمدی");

  fireEvent.click(screen.getByRole("button", { name: /سبد خرید/ }));
  fireEvent.click(await screen.findByRole("link", { name: /مشاهدهٔ سبد و ثبت سفارش/ }));
  await screen.findByRole("heading", { name: "سبد خرید" });
  fireEvent.click(screen.getByRole("button", { name: "ادامه و ثبت سفارش" }));
  await screen.findByRole("heading", { name: "ثبت سفارش" });

  // The newly saved address is available and selected in saved-address mode.
  await waitFor(() => {
    expect(screen.getByRole("radio", { name: /سارا احمدی/ }).checked).toBe(true);
  });
}

function renderLoggedInApp() {
  return render(
    <MemoryRouter initialEntries={["/account/addresses/"]}>
      <App />
    </MemoryRouter>
  );
}

beforeEach(() => {
  document.cookie = "csrftoken=flow-csrf";
  useAuthStore.setState({
    user: CUSTOMER,
    isAuthenticated: true,
    isLoading: false,
    error: null,
    sessionExpired: false,
  });
  useCartStore.setState({
    cart: CART,
    guestLines: [],
    guestProducts: {},
    guestVariants: {},
    guestHydration: "ready",
    guestHydrationError: null,
    isLoading: false,
    error: null,
  });
});

afterEach(() => {
  cleanup();
  apiClient.defaults.adapter = originalAdapter;
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, error: null });
  useCartStore.setState({ cart: null, guestLines: [], guestProducts: {}, guestVariants: {}, error: null });
  document.cookie = "csrftoken=; Max-Age=0";
});

describe("saved-address checkout flow", () => {
  it.each([
    ["courier", "standard"],
    ["pickup", "pickup"],
  ])("creates an address from the paginated endpoint and places a %s order", async (_label, method) => {
    const addresses = [];
    const checkoutPayloads = [];
    let nextAddressId = 1;

    apiClient.defaults.adapter = async (config) => {
      const url = config.url || "";
      const requestMethod = (config.method || "get").toLowerCase();
      const csrf = config.headers?.["X-CSRFToken"] || config.headers?.get?.("X-CSRFToken");
      if (["post", "patch", "delete"].includes(requestMethod) && csrf !== "flow-csrf") {
        throw new Error(`missing CSRF header for ${requestMethod} ${url}`);
      }

      if (url === "/accounts/me/") return ok(CUSTOMER, config);
      if (url === "/accounts/locations/") return ok({ provinces: [] }, config);
      if (url === "/accounts/addresses/" && requestMethod === "get") return ok(page(addresses), config);
      if (url === "/accounts/addresses/" && requestMethod === "post") {
        const body = JSON.parse(config.data || "{}");
        const address = { id: nextAddressId++, ...body, is_default: addresses.length === 0 };
        addresses.push(address);
        return ok(address, config);
      }
      if (url === "/categories/tree/") return ok(page([]), config);
      if (url === "/cart/") return ok(CART, config);
      if (url === "/site/settings/") return ok({}, config);
      if (url === "/orders/shipping-methods/") return ok(SHIPPING, config);
      if (url === "/orders/checkout/" && requestMethod === "post") {
        const body = JSON.parse(config.data || "{}");
        checkoutPayloads.push(body);
        return ok(
          {
            id: 81,
            order_number: "CG-FLOW-81",
            subtotal: 250000,
            discount_amount: 0,
            shipping_cost: body.shipping_method === "pickup" ? 0 : 45000,
            gift_wrap_fee: 0,
            total: body.shipping_method === "pickup" ? 250000 : 295000,
            shipping_method: body.shipping_method,
          },
          config
        );
      }
      if (url === "/products/") return ok(page([]), config);
      return ok({}, config);
    };

    renderLoggedInApp();
    await addAddressThenOpenCheckout();

    if (method === "pickup") {
      fireEvent.click(screen.getByRole("radio", { name: /دریافت حضوری/ }));
      fireEvent.change(await screen.findByLabelText(/^نام تحویل‌گیرنده/), { target: { value: "سارا" } });
      fireEvent.change(screen.getByLabelText(/^شماره تماس/), { target: { value: "09121112233" } });
    }

    fireEvent.click(screen.getByRole("button", { name: /ثبت سفارش/ }));
    await waitFor(() => expect(checkoutPayloads).toHaveLength(1));
    await screen.findByRole("heading", { name: "سفارش شما ثبت شد" });

    if (method === "pickup") {
      expect(checkoutPayloads[0]).toMatchObject({
        recipient_name: "سارا",
        phone: "09121112233",
        shipping_method: "pickup",
      });
    } else {
      expect(checkoutPayloads[0]).toEqual({ address_id: 1, shipping_method: "standard" });
    }
  });
});
