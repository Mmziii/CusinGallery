/**
 * Part S1 item 2: "cart page does not fully render on first visit".
 *
 * The guest cart stores only product ids; names/prices/images arrive via
 * the products API AFTER mount. These tests reproduce the owner's flow
 * (open home -> add a product -> go to cart) against a SLOW and then a
 * FAILING hydration request, and verify:
 *   - skeleton rows (not half-rendered lines with a fake 0 total) while
 *     the products request is in flight;
 *   - no computed total is shown until every line is hydrated;
 *   - on failure a friendly error + working retry appears (never a
 *     permanently half-rendered page);
 *   - a stale response can not overwrite a newer hydration.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import useCartStore from "../store/useCartStore";
import CartPage from "./CartPage";

const product = (id, name, price) => ({
  id,
  name,
  slug: `p-${id}`,
  price,
  primary_image: null,
  price_info: { price, compare_at_price: null, discount_percentage: 0, is_on_sale: false, discount_amount: 0 },
  stock_status: "in_stock",
  is_in_stock: true,
});

// Per-request behavior queue: each /products/ call shifts one mode.
let hydrateModes = [];
const slowReleases = []; // resolvers for "slow" requests, in arrival order
const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (url === "/products/") {
      const mode = hydrateModes.shift() || "fast";
      const ids = String((config.params || {}).ids || "");
      const rows = ids.split(",").filter(Boolean).map((id) => product(Number(id), `کالای ${id}`, 50000));
      if (mode === "fail") {
        const err = new Error("network down");
        err.response = undefined; // pure network failure
        throw err;
      }
      if (mode === "slow") {
        await new Promise((resolve) => slowReleases.push(resolve));
      }
      return {
        data: { count: rows.length, next: null, previous: null, results: rows },
        status: 200, statusText: "OK", headers: {}, config,
      };
    }
    return originalAdapter(config);
  };
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
beforeEach(async () => {
  localStorage.clear();
  hydrateModes = [];
  slowReleases.length = 0;
  useCartStore.setState({
    guestLines: [], guestProducts: {}, guestHydration: "idle", guestHydrationError: null,
    cart: null, error: null,
  });
  const authStore = await import("../store/useAuthStore");
  authStore.default.setState({ isAuthenticated: false, isLoading: false });
});
afterEach(() => cleanup());

function seedGuestCart(productIds) {
  const lines = productIds.map((id) => ({ product_id: id, variant_id: null, quantity: 1 }));
  localStorage.setItem("cusin.guest_cart.v1.lines", JSON.stringify(lines));
  useCartStore.setState({ guestLines: lines });
}

function renderCart() {
  return render(
    <MemoryRouter initialEntries={["/cart/"]}>
      <CartPage />
    </MemoryRouter>
  );
}

describe("guest cart hydration (S1 item 2)", () => {
  it("shows skeletons and no fake total while the products request is in flight", async () => {
    hydrateModes = ["slow"];
    seedGuestCart([101, 102]);
    renderCart();

    // While in flight: skeleton + explicit loading note, no misleading total.
    expect(await screen.findByText("در حال دریافت اطلاعات کالاها…")).toBeTruthy();
    expect(document.querySelector(".cart-item--skeleton")).toBeTruthy();
    expect(screen.queryByText(/جمع کالاها/)).toBeNull();

    await waitFor(() => expect(slowReleases.length).toBe(1));
    slowReleases[0]();
    expect(await screen.findByText("کالای 101")).toBeTruthy();
    expect(await screen.findByText("کالای 102")).toBeTruthy();
    // Part S5 follow-up 4 item 3: once every line is hydrated the summary
    // shows the products subtotal (and nothing else) with a real number.
    expect(await screen.findByText(/جمع کالاها/)).toBeTruthy();
    expect(screen.queryByText("در حال محاسبه")).toBeNull();
  });

  it("shows a friendly error with a working retry when hydration fails", async () => {
    hydrateModes = ["fail", "fast"];
    seedGuestCart([101]);
    renderCart();

    expect(await screen.findByText("دریافت اطلاعات کالاها با خطا مواجه شد.")).toBeTruthy();
    expect(screen.queryByText("کالای 101")).toBeNull();

    fireEvent.click(screen.getByText("تلاش دوباره"));
    expect(await screen.findByText("کالای 101")).toBeTruthy();
    expect(screen.queryByText("دریافت اطلاعات کالاها با خطا مواجه شد.")).toBeNull();
  });

  it("never stores a stale hydration result over a newer one", async () => {
    // Two hydrations race: the first (slow) resolves AFTER the second.
    hydrateModes = ["slow", "fast"];
    seedGuestCart([1]);
    const first = useCartStore.getState().hydrateGuestProducts();

    useCartStore.setState({ guestLines: [{ product_id: 2, variant_id: null, quantity: 1 }] });
    const second = useCartStore.getState().hydrateGuestProducts(); // fast: id=2
    await second;

    // Now let the stale first request finish; it must be ignored.
    await waitFor(() => expect(slowReleases.length).toBe(1));
    slowReleases[0]();
    await first;

    const { guestProducts } = useCartStore.getState();
    expect(Object.keys(guestProducts)).toEqual(["2"]);
    expect(guestProducts["1"]).toBeUndefined();
  });

  it("renders an authenticated cart with a spinner then the full cart", async () => {
    // Authenticated path: server cart comes back in one piece.
    const authStore = await import("../store/useAuthStore");
    authStore.default.setState({ isAuthenticated: true, isLoading: false });
    let releaseCart = null;
    const prev = apiClient.defaults.adapter;
    apiClient.defaults.adapter = async (config) => {
      if ((config.url || "") === "/cart/" && (config.method || "get").toLowerCase() === "get") {
        await new Promise((resolve) => {
          releaseCart = resolve;
        });
        return {
          data: {
            items: [
              {
                id: 5, quantity: 1, is_available: true, unavailable_reason: null,
                product: { id: 9, name: "کالای سروری", slug: "p-9", primary_image: null },
                variant: null,
                price_info: { price: 70000, compare_at_price: null, discount_percentage: 0, is_on_sale: false, discount_amount: 0 },
                line_total: 70000,
              },
            ],
            item_count: 1, subtotal: 70000, total: 70000,
          },
          status: 200, statusText: "OK", headers: {}, config,
        };
      }
      return prev(config);
    };

    renderCart();
    expect(await screen.findByText("در حال دریافت سبد خرید…")).toBeTruthy();
    releaseCart();
    expect(await screen.findByText("کالای سروری")).toBeTruthy();

    apiClient.defaults.adapter = prev;
  });
});
