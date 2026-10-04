/**
 * Guest-cart store tests (Part 1): localStorage persistence, quantity
 * editing, merge-on-login behaviour (clear local lines ONLY on success,
 * keep them on failure) and token rotation for idempotency.
 */
import { beforeEach, describe, expect, it } from "vitest";

import useCartStore from "./useCartStore";
import { getMergeToken, loadGuestLines } from "../utils/guestCart";

function resetStore() {
  window.localStorage.clear();
  useCartStore.setState({
    cart: null,
    guestLines: [],
    guestProducts: {},
    lastMergeReport: null,
    isLoading: false,
    error: null,
  });
}

beforeEach(resetStore);

describe("guest cart store", () => {
  it("adds and persists guest lines to localStorage (ids+qty only)", () => {
    useCartStore.getState().addGuestItem(101, null, 2);
    useCartStore.getState().addGuestItem(101, null, 1);
    useCartStore.getState().addGuestItem(102, 5, 1);

    const stored = loadGuestLines();
    expect(stored).toEqual([
      { product_id: 101, variant_id: null, quantity: 3 },
      { product_id: 102, variant_id: 5, quantity: 1 },
    ]);
    // The badge view mirrors the stored lines.
    expect(useCartStore.getState().cart.item_count).toBe(4);
    // Nothing price-like ever lands in storage.
    expect(JSON.stringify(stored)).not.toContain("price");
  });

  it("updates and removes guest lines", () => {
    useCartStore.getState().addGuestItem(101, null, 3);
    useCartStore.getState().updateGuestItem(101, null, 1);
    expect(loadGuestLines()[0].quantity).toBe(1);
    useCartStore.getState().updateGuestItem(101, null, 0);
    expect(loadGuestLines()).toEqual([]);
  });

  it("merge success clears the local cart and reports adjustments", async () => {
    useCartStore.getState().addGuestItem(101, null, 2);
    useCartStore.getState().addGuestItem(7001, null, 5); // capped at 2 by fake server
    useCartStore.getState().addGuestItem(8001, null, 1); // out of stock

    const report = await useCartStore.getState().mergeGuestCart();

    expect(report.merged[0].added).toBe(2);
    expect(report.adjusted[0].added).toBe(2);
    expect(report.skipped[0].reason).toBe("out_of_stock");
    expect(loadGuestLines()).toEqual([]);
    expect(useCartStore.getState().guestLines).toEqual([]);
    expect(useCartStore.getState().cart.item_count).toBe(4); // 2 + capped 2
  });

  it("a failed merge NEVER loses the guest cart", async () => {
    useCartStore.getState().addGuestItem(101, null, 2);
    useCartStore.getState().addGuestItem(9999, null, 1); // fake-server outage trigger
    const report = await useCartStore.getState().mergeGuestCart();
    expect(report.error).toBeTruthy();
    // The local cart is untouched -- next login attempt retries it.
    expect(loadGuestLines().length).toBe(2);
    expect(useCartStore.getState().guestLines.length).toBe(2);
  });

  it("rotates the merge token after success (double-merge safe)", async () => {
    useCartStore.getState().addGuestItem(101, null, 1);
    const tokenBefore = getMergeToken();
    await useCartStore.getState().mergeGuestCart();
    expect(getMergeToken()).not.toBe(tokenBefore);
  });
});
