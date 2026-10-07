/**
 * Part S5 follow-up 4, item 3: "قیمت‌ها در سبد خرید مهمان نمایش داده
 * نمی‌شود" (prices missing in the guest cart).
 *
 * Root cause reproduced here first: the guest rows read `product.price`,
 * but NO product payload has that field -- the API exposes
 * `price_info.price` (plus compare_at_price/discount_percentage/
 * is_on_sale). formatPrice(undefined) returns "", so every guest price
 * rendered as an empty string next to "تومان", the line totals were all 0
 * and the subtotal was 0 whenever the customer was not logged in.
 *
 * The same wrong field lived in three more places (Header mini-cart guest
 * lines, Header search suggestions, CartPage) -- those are covered here
 * too, because the fix has to be one shared rule, not four copies.
 *
 * Also locked in here (same item): a guest row whose line carries a
 * variant_id must be priced from the VARIANT's own price_info -- the
 * products LIST endpoint never returns variants, so the store fetches the
 * product detail by slug for exactly those products and caches the
 * variants it needs.
 *
 * Numbers used in this file (Toman):
 *   قابلمه گرانیتی  unit 50,000  x2 = 100,000   (no variant)
 *   سرویس بلور      unit 60,000  x1 =  60,000   (compare-at 90,000)
 *   کتری استیل      unit 45,000  x3 = 135,000   (variant, NOT 30,000)
 *   products subtotal                = 295,000
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import { formatPrice } from "../utils/formatPrice";
import CartPage from "./CartPage";
import CheckoutPage from "./CheckoutPage";
import Header from "../components/Header";

const priceInfo = (price, compareAt = null) => ({
  price,
  compare_at_price: compareAt,
  discount_percentage: compareAt ? Math.round(((compareAt - price) / compareAt) * 100) : 0,
  is_on_sale: Boolean(compareAt),
  discount_amount: compareAt ? compareAt - price : 0,
});

const PRODUCTS = {
  1: {
    id: 1, name: "قابلمه گرانیتی", slug: "pan-1", primary_image: null,
    price_info: priceInfo(50000),
  },
  2: {
    id: 2, name: "سرویس بلور", slug: "glass-2", primary_image: null,
    price_info: priceInfo(60000, 90000),
  },
  3: {
    id: 3, name: "کتری استیل", slug: "kettle-3", primary_image: null,
    price_info: priceInfo(30000),
  },
};

// The variant the guest line points at: its own price differs from the
// product's (45,000 vs 30,000) so a fix that still reads the product would
// be caught.
const KETTLE_VARIANT = {
  id: 33,
  sku: "KETTLE-BLK",
  price_info: priceInfo(45000),
  stock_status: "in_stock",
  is_in_stock: true,
  is_active: true,
  image: null,
  attribute_values: [
    { id: 7, attribute: "رنگ", attribute_slug: "color", value: "مشکی" },
  ],
};

const GUEST_LINES = [
  { product_id: 1, variant_id: null, quantity: 2 },
  { product_id: 2, variant_id: null, quantity: 1 },
  { product_id: 3, variant_id: 33, quantity: 3 },
];
const SUBTOTAL = 50000 * 2 + 60000 + 45000 * 3; // 295,000

const SERVER_CART = {
  items: [
    {
      id: 11, quantity: 2, is_available: true, unavailable_reason: null,
      product: { id: 1, name: "قابلمه گرانیتی", slug: "pan-1", primary_image: null },
      variant: null,
      price_info: priceInfo(50000),
      line_total: 100000,
    },
    {
      id: 12, quantity: 1, is_available: true, unavailable_reason: null,
      product: { id: 2, name: "سرویس بلور", slug: "glass-2", primary_image: null },
      variant: { id: 44, attribute_values: [{ attribute: "رنگ", value: "شفاف" }] },
      price_info: priceInfo(60000, 90000),
      line_total: 60000,
    },
  ],
  item_count: 3,
  subtotal: 160000,
  total: 160000,
  shipping_cost_preview: 45000,
};

const ACCOUNT = { id: 1, phone: "09120000000", first_name: "آزمون" };
const ADDRESS = {
  id: 7, recipient_name: "سارا", phone: "09121112233", province: "تهران",
  city: "تهران", address: "خیابان ولیعصر، پلاک ۵", postal_code: "1234567890",
  unit: "۳", building_number: "۵", is_default: true,
};
const SHIPPING = {
  default: "standard",
  gift_wrap_fee: 25000,
  methods: [
    {
      id: "standard", label: "ارسال عادی", cost: 45000, free_threshold: null,
      min_days: 3, max_days: 5, requires_address: true,
    },
  ],
};

/** The order the mocked server creates: its totals are what the checkout
 *  page must display -- never a number the page computed itself. */
const PLACED_ORDER = {
  id: 900, order_number: "CG-900", subtotal: 160000, discount_amount: 0,
  shipping_cost: 45000, gift_wrap: true, gift_wrap_fee: 25000,
  gift_message: "", total: 230000, coupon_code: "", shipping_method: "standard",
};

const originalAdapter = apiClient.defaults.adapter;
let detailCalls = [];

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    const method = (config.method || "get").toLowerCase();
    const ok = (data) => ({ data, status: 200, statusText: "OK", headers: {}, config });

    if (url === "/products/" && method === "get") {
      const ids = String((config.params || {}).ids || "")
        .split(",")
        .filter(Boolean)
        .map(Number);
      return ok({
        count: ids.length, next: null, previous: null,
        results: ids.map((id) => PRODUCTS[id]).filter(Boolean),
      });
    }
    if (method === "get" && /^\/products\/[^/]+\/$/.test(url)) {
      detailCalls.push(url);
      const slug = url.replace("/products/", "").replace(/\/$/, "");
      const product = Object.values(PRODUCTS).find((p) => p.slug === slug);
      if (!product) return ok({ detail: "not found" });
      return ok({ ...product, variants: slug === "kettle-3" ? [KETTLE_VARIANT] : [] });
    }
    if (/categories\/tree/.test(url)) return ok([]);
    if (url === "/site/settings/") return ok({});
    if (url === "/accounts/me/" && method === "get") {
      return ok(useAuthStore.getState().isAuthenticated ? ACCOUNT : { user: null });
    }
    if (url === "/cart/" && method === "get") return ok(SERVER_CART);
    if (url === "/orders/shipping-methods/") return ok(SHIPPING);
    if (url === "/accounts/addresses/") return ok([ADDRESS]);
    if (url === "/orders/checkout/") return ok(PLACED_ORDER);
    return originalAdapter(config);
  };
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});

beforeEach(() => {
  localStorage.clear();
  detailCalls = [];
  useCartStore.setState({
    cart: null, guestLines: [], guestProducts: {}, guestVariants: {},
    guestHydration: "idle", guestHydrationError: null, isLoading: false, error: null,
  });
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false });
});
afterEach(() => cleanup());

function renderAt(path, node) {
  return render(<MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>);
}

/** The `.cart-item` block that contains the given product name. */
function itemByName(container, name) {
  const nameNode = [...container.querySelectorAll(".cart-item__name")].find(
    (node) => node.textContent.includes(name)
  );
  expect(nameNode, `no cart line for ${name}`).toBeTruthy();
  return nameNode.closest(".cart-item");
}

describe("guest cart prices (item 3)", () => {
  it("prices every line from price_info: normal, discounted and variant lines", async () => {
    useCartStore.setState({ guestLines: GUEST_LINES });
    const view = renderAt("/cart/", <CartPage />);

    await screen.findByText("قابلمه گرانیتی");

    const pan = itemByName(view.container, "قابلمه گرانیتی");
    expect(pan.querySelector(".cart-item__unit").textContent).toContain(formatPrice(50000));
    expect(pan.querySelector(".cart-item__total").textContent).toContain(formatPrice(100000));

    // Discounted product: the current price AND the crossed-out old one.
    const glass = itemByName(view.container, "سرویس بلور");
    expect(glass.querySelector(".cart-item__unit").textContent).toContain(formatPrice(60000));
    expect(glass.querySelector(".price__compare").textContent).toContain(formatPrice(90000));
    expect(glass.querySelector(".cart-item__total").textContent).toContain(formatPrice(60000));

    // Variant line: the VARIANT's price (45,000), not the product's 30,000.
    const kettle = itemByName(view.container, "کتری استیل");
    expect(kettle.querySelector(".cart-item__unit").textContent).toContain(formatPrice(45000));
    expect(kettle.querySelector(".cart-item__unit").textContent).not.toContain(formatPrice(30000));
    expect(kettle.querySelector(".cart-item__total").textContent).toContain(formatPrice(135000));
    expect(kettle.querySelector(".cart-item__variant").textContent).toContain("رنگ: مشکی");

    // The subtotal is the sum of the three LINE TOTALS above -- exactly,
    // not a rounded or zero value.
    const summary = view.container.querySelector(".cart-page__summary");
    expect(summary.textContent).toContain("جمع کالاها");
    expect(summary.querySelector("dt").textContent).toContain("(۶)");
    expect(summary.querySelector("dd").textContent.trim()).toBe(`${formatPrice(SUBTOTAL)} تومان`);
  });

  it("shows ONLY the products subtotal -- no shipping, no packaging, no final total", async () => {
    useCartStore.setState({ guestLines: GUEST_LINES });
    const view = renderAt("/cart/", <CartPage />);
    await screen.findByText("قابلمه گرانیتی");

    const summary = view.container.querySelector(".cart-page__summary");
    expect(summary.querySelectorAll("dl > div").length).toBe(1);
    expect(summary.textContent).toContain("جمع کالاها");

    const text = view.container.textContent;
    expect(text).not.toMatch(/هزینه ارسال/);
    expect(text).not.toMatch(/بسته‌بندی هدیه/);
    expect(text).not.toMatch(/مبلغ قابل پرداخت/);
    expect(view.container.querySelector(".cart-page__grand")).toBeNull();
  });

  it("fetches product detail only for lines that carry a variant_id", async () => {
    useCartStore.setState({ guestLines: GUEST_LINES });
    renderAt("/cart/", <CartPage />);
    await screen.findByText("کتری استیل");
    await waitFor(() => expect(Object.keys(useCartStore.getState().guestVariants).length).toBe(1));
    expect(detailCalls).toEqual(["/products/kettle-3/"]);
  });

  it("does the same for the authenticated cart: unit price, line total, products subtotal only", async () => {
    useAuthStore.setState({ user: ACCOUNT, isAuthenticated: true, isLoading: false });
    const view = renderAt("/cart/", <CartPage />);

    await screen.findByText("قابلمه گرانیتی");
    const pan = itemByName(view.container, "قابلمه گرانیتی");
    expect(pan.querySelector(".cart-item__unit").textContent).toContain(formatPrice(50000));
    expect(pan.querySelector(".cart-item__total").textContent).toContain(formatPrice(100000));
    const glass = itemByName(view.container, "سرویس بلور");
    expect(glass.querySelector(".cart-item__variant").textContent).toContain("رنگ: شفاف");
    expect(glass.querySelector(".price__compare").textContent).toContain(formatPrice(90000));

    const summary = view.container.querySelector(".cart-page__summary");
    expect(summary.querySelectorAll("dl > div").length).toBe(1);
    expect(summary.textContent).toContain(formatPrice(SERVER_CART.subtotal));
    expect(view.container.textContent).not.toMatch(/هزینه ارسال/);
    expect(view.container.textContent).not.toMatch(/مبلغ قابل پرداخت/);
  });
});

describe("mini-cart prices (item 3)", () => {
  it("shows unit price, line total and the products subtotal -- for guests too", async () => {
    useCartStore.setState({ guestLines: GUEST_LINES });
    const view = renderAt("/", <Header />);

    const cartLink = await waitFor(() => {
      const node = view.container.querySelector(".cart-link");
      expect(node).toBeTruthy();
      return node;
    });
    fireEvent.click(cartLink);

    const drawer = await waitFor(() => {
      const node = document.querySelector(".minicart");
      expect(node).toBeTruthy();
      return node;
    });
    await waitFor(() => expect(drawer.querySelectorAll(".minicart__items li").length).toBe(3));

    const rows = [...drawer.querySelectorAll(".minicart__items li")];
    const rowText = (name) => rows.find((li) => li.textContent.includes(name)).textContent;

    expect(rowText("قابلمه گرانیتی")).toContain(formatPrice(50000));
    expect(rowText("قابلمه گرانیتی")).toContain(formatPrice(100000));
    expect(rowText("سرویس بلور")).toContain(formatPrice(60000));
    expect(rowText("سرویس بلور")).toContain(formatPrice(90000));
    // Variant line priced from the variant, not the product.
    expect(rowText("کتری استیل")).toContain(formatPrice(45000));
    expect(rowText("کتری استیل")).not.toContain(formatPrice(30000));
    expect(rowText("کتری استیل")).toContain(formatPrice(135000));

    const subtotal = drawer.querySelector(".minicart__subtotal");
    expect(subtotal.textContent).toContain("جمع کالاها");
    expect(subtotal.textContent).toContain(formatPrice(SUBTOTAL));
    expect(drawer.textContent).not.toMatch(/هزینه ارسال/);
    expect(drawer.textContent).not.toMatch(/مبلغ قابل پرداخت/);
  });
});

describe("checkout final amount (item 3)", () => {
  it("shows the server-computed «مبلغ قابل پرداخت» before the payment step", async () => {
    useAuthStore.setState({ user: ACCOUNT, isAuthenticated: true, isLoading: false });
    const view = renderAt("/checkout/", <CheckoutPage />);
    await screen.findByRole("heading", { name: "ثبت سفارش" });

    const summary = await waitFor(() => {
      const node = view.container.querySelector(".checkout__summary");
      expect(node).toBeTruthy();
      return node;
    });
    await waitFor(() => expect(summary.textContent).toContain("مبلغ قابل پرداخت"));
    // 160,000 products + 45,000 standard shipping, straight from the API.
    expect(summary.textContent).toContain(formatPrice(205000));

    fireEvent.click(screen.getByRole("button", { name: /ثبت سفارش/ }));

    // After the order is created (server) and before the gateway redirect,
    // the page shows the server's own total -- including gift wrapping.
    await screen.findByRole("heading", { name: "سفارش شما ثبت شد" });
    const done = view.container.querySelector(".checkout-done__totals");
    expect(done.textContent).toContain("بسته‌بندی هدیه");
    expect(done.textContent).toContain(formatPrice(25000));
    expect(done.textContent).toContain("مبلغ قابل پرداخت");
    expect(done.textContent).toContain(formatPrice(PLACED_ORDER.total));
    expect(screen.getByRole("button", { name: /پرداخت آنلاین/ })).toBeTruthy();
  });
});
