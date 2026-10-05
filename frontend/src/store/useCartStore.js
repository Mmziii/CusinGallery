import { create } from "zustand";

import * as cartApi from "../services/cartApi";
import * as catalogApi from "../services/catalogApi";
import { normalizeApiError } from "../utils/apiError";
import {
  clearGuestLines,
  getMergeToken,
  guestLineCount,
  loadGuestLines,
  rotateMergeToken,
  saveGuestLines,
} from "../utils/guestCart";

/**
 * Cart state store.
 *
 * Authenticated users: the backend stays authoritative -- every action
 * calls the API and stores the FRESH server response; this store never
 * computes prices.
 *
 * Guests (Part 1): lines live in localStorage as {product_id,
 * variant_id, quantity} ONLY. Names/prices for display are hydrated
 * from the products API (hydrateGuestProducts) and never persisted.
 * On login/register the guest lines are merged server-side through
 * POST /cart/merge/ (idempotent per merge_token); the local cart is
 * cleared ONLY after a successful merge, so a failed network call can
 * never lose it.
 *
 * `cart` always holds a badge-compatible view: the server payload for
 * logged-in users, or a synthesized {items, item_count} for guests.
 */
// Part S1 item 2: hydration requests are sequenced so a stale response
// (slow network, fast repeated cart changes, navigation) can never
// overwrite the result of a newer request.
let hydrationSeq = 0;

const useCartStore = create((set, get) => ({
  cart: null,
  guestLines: loadGuestLines(),
  guestProducts: {}, // product_id -> product payload (display-only)
  // Part S1 item 2: explicit hydration lifecycle so the cart page never
  // shows half-rendered rows with a fake 0 total: "idle" before the
  // first attempt, "loading" in flight, "ready" once hydrated, "error"
  // when the products request failed (retry via hydrateGuestProducts()).
  guestHydration: "idle",
  guestHydrationError: null,
  lastMergeReport: null,
  isLoading: false,
  error: null,

  _guestCartView(lines) {
    return { items: lines, item_count: guestLineCount(lines), guest: true };
  },

  _syncGuest() {
    const lines = get().guestLines;
    saveGuestLines(lines);
    set({ cart: get()._guestCartView(lines) });
  },

  // ------------------------------------------------ guest actions
  addGuestItem(productId, variantId, quantity) {
    const lines = [...get().guestLines];
    const existing = lines.find(
      (l) => l.product_id === productId && (l.variant_id ?? null) === (variantId ?? null)
    );
    if (existing) {
      existing.quantity += quantity;
    } else {
      lines.push({ product_id: productId, variant_id: variantId ?? null, quantity });
    }
    set({ guestLines: lines });
    get()._syncGuest();
    return { success: true };
  },

  updateGuestItem(productId, variantId, quantity) {
    let lines = [...get().guestLines];
    if (quantity <= 0) {
      lines = lines.filter(
        (l) => !(l.product_id === productId && (l.variant_id ?? null) === (variantId ?? null))
      );
    } else {
      const existing = lines.find(
        (l) => l.product_id === productId && (l.variant_id ?? null) === (variantId ?? null)
      );
      if (existing) existing.quantity = quantity;
    }
    set({ guestLines: lines });
    get()._syncGuest();
    return { success: true };
  },

  async hydrateGuestProducts() {
    const ids = [...new Set(get().guestLines.map((l) => l.product_id))];
    if (ids.length === 0) {
      set({ guestProducts: {}, guestHydration: "ready", guestHydrationError: null });
      return;
    }
    const seq = ++hydrationSeq;
    set({ guestHydration: "loading", guestHydrationError: null });
    try {
      const data = await catalogApi.listProducts({ ids: ids.join(","), page_size: ids.length });
      if (seq !== hydrationSeq) return; // a newer request owns the result
      const byId = {};
      for (const product of data.results || []) byId[product.id] = product;
      set({ guestProducts: byId, guestHydration: "ready", guestHydrationError: null });
    } catch (err) {
      if (seq !== hydrationSeq) return; // a newer request owns the state
      // Never swallow: the cart page shows a friendly error + retry, and
      // already-hydrated rows keep their data (guestProducts untouched).
      set({ guestHydration: "error", guestHydrationError: normalizeApiError(err) });
    }
  },

  async mergeGuestCart() {
    const lines = get().guestLines;
    if (lines.length === 0) return null;
    try {
      const response = await cartApi.mergeGuestCart(lines, getMergeToken());
      // Success is the ONLY path that clears the guest cart: a lost or
      // failed response leaves the lines intact for the next attempt.
      clearGuestLines();
      rotateMergeToken();
      set({
        guestLines: [],
        cart: response.cart,
        lastMergeReport: response.report,
        error: null,
      });
      return response.report;
    } catch (err) {
      // Keep the local cart; surface nothing destructive.
      set({ lastMergeReport: null });
      return { error: normalizeApiError(err) };
    }
  },

  clearMergeNotice() {
    set({ lastMergeReport: null });
  },

  // ------------------------------------------------ server actions
  async fetchCart() {
    set({ isLoading: true, error: null });
    try {
      const cart = await cartApi.fetchCart();
      set({ cart, isLoading: false });
    } catch (err) {
      set({ isLoading: false, error: normalizeApiError(err) });
    }
  },

  async addItem(productId, variantId, quantity) {
    const { isAuthenticated } = (await import("./useAuthStore")).default.getState();
    if (!isAuthenticated) return get().addGuestItem(productId, variantId, quantity);
    set({ isLoading: true, error: null });
    try {
      const cart = await cartApi.addCartItem(productId, variantId, quantity);
      set({ cart, isLoading: false });
      return { success: true };
    } catch (err) {
      const normalized = normalizeApiError(err);
      set({ isLoading: false, error: normalized });
      return { success: false, error: normalized };
    }
  },

  async updateItem(itemId, quantity, guestKey = null) {
    if (guestKey) {
      return get().updateGuestItem(guestKey.product_id, guestKey.variant_id, quantity);
    }
    set({ isLoading: true, error: null });
    try {
      const cart = await cartApi.updateCartItem(itemId, quantity);
      set({ cart, isLoading: false });
      return { success: true };
    } catch (err) {
      const normalized = normalizeApiError(err);
      set({ isLoading: false, error: normalized });
      return { success: false, error: normalized };
    }
  },

  async removeItem(itemId, guestKey = null) {
    if (guestKey) {
      return get().updateGuestItem(guestKey.product_id, guestKey.variant_id, 0);
    }
    set({ isLoading: true, error: null });
    try {
      const cart = await cartApi.removeCartItem(itemId);
      set({ cart, isLoading: false });
      return { success: true };
    } catch (err) {
      const normalized = normalizeApiError(err);
      set({ isLoading: false, error: normalized });
      return { success: false, error: normalized };
    }
  },

  /**
   * Called on logout: drop the SERVER cart view but keep the
   * browser-level guest lines (they belong to the device, not to any
   * user, and can never contain another user's server cart).
   */
  reset() {
    set({ cart: null, error: null, guestProducts: {} });
    const lines = get().guestLines;
    if (lines.length > 0) set({ cart: get()._guestCartView(lines) });
  },
}));

export default useCartStore;
