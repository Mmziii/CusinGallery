/**
 * Part S2 item 6: optimistic quantity updates + rollback.
 *
 * The store must react INSTANTLY to +/- clicks (UI updates before the
 * server answers) and must restore the exact pre-change cart when the
 * request fails -- a slow or failing network may never leave the cart
 * showing numbers the server did not confirm.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import useCartStore from "./useCartStore";

const serverCart = () => ({
  items: [
    {
      id: 11,
      quantity: 2,
      line_total: 20000,
      price_info: { price: 10000 },
      product: { id: 1, name: "کالای یک", slug: "p1" },
      is_available: true,
    },
    {
      id: 12,
      quantity: 1,
      line_total: 5000,
      price_info: { price: 5000 },
      product: { id: 2, name: "کالای دو", slug: "p2" },
      is_available: true,
    },
  ],
  item_count: 3,
  subtotal: 25000,
});

let nextUpdate = { mode: "ok" }; // ok | slow | fail
let releases = [];
const originalAdapter = apiClient.defaults.adapter;

function seed() {
  useCartStore.setState({ cart: serverCart(), guestLines: [], guestProducts: {}, error: null });
}

beforeEach(() => {
  seed();
  releases = [];
  nextUpdate = { mode: "ok" };
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (url.startsWith("/cart/items/")) {
      const mode = nextUpdate.mode;
      if (mode === "slow") {
        await new Promise((resolve) => {
          releases.push(resolve);
        });
      }
      if (mode === "fail") {
        const err = new Error("network down");
        err.response = undefined;
        throw err;
      }
      return {
        data: serverCart(),
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      };
    }
    return originalAdapter(config);
  };
});

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
});

describe("optimistic cart updates (S2.6)", () => {
  it("updates the UI instantly, before the server responds", async () => {
    nextUpdate = { mode: "slow" };
    const promise = useCartStore.getState().updateItem(11, 4);
    // Let the async chain run into the adapter so the request parks.
    await new Promise((resolve) => setTimeout(resolve, 0));

    // Optimistic state is already visible while the request is in flight.
    const optimistic = useCartStore.getState().cart;
    const line = optimistic.items.find((item) => item.id === 11);
    expect(line.quantity).toBe(4);
    expect(line.line_total).toBe(40000); // price x qty, display-only
    expect(optimistic.subtotal).toBe(45000);
    expect(optimistic.item_count).toBe(5);

    releases.shift()();
    const result = await promise;
    expect(result.success).toBe(true);
    // Server truth replaces the optimistic view.
    expect(useCartStore.getState().cart.items.find((item) => item.id === 11).quantity).toBe(2);
  });

  it("rolls back to the exact pre-change cart when the update fails", async () => {
    nextUpdate = { mode: "fail" };
    const before = useCartStore.getState().cart;

    const result = await useCartStore.getState().updateItem(11, 9);

    expect(result.success).toBe(false);
    expect(useCartStore.getState().cart).toEqual(before);
    expect(useCartStore.getState().error).toBeTruthy();
  });

  it("removes a line optimistically and restores it on failure", async () => {
    nextUpdate = { mode: "fail" };
    const before = useCartStore.getState().cart;

    const result = await useCartStore.getState().removeItem(12);

    expect(result.success).toBe(false);
    // Rolled back: the removed line is back with its original numbers.
    expect(useCartStore.getState().cart).toEqual(before);
  });

  it("removes a line optimistically and keeps server state on success", async () => {
    nextUpdate = { mode: "slow" };
    const promise = useCartStore.getState().removeItem(12);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(useCartStore.getState().cart.items.map((item) => item.id)).toEqual([11]);
    expect(useCartStore.getState().cart.item_count).toBe(2);

    releases.shift()();
    const result = await promise;
    expect(result.success).toBe(true);
  });
});
