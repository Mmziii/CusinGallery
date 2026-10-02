import { create } from "zustand";

import * as cartApi from "../services/cartApi";
import { normalizeApiError } from "../utils/apiError";

/**
 * Cart state store (Phase 5) -- fulfills exactly what useUIStore.js's
 * own docstring predicted back in Phase 1: "cart... state [is]
 * server-backed and will get [its] own store module in Phase 5 that
 * call[s] the API via src/services/*, rather than holding authoritative
 * data client-side."
 *
 * The backend remains authoritative for every price/quantity/
 * availability value: every action below calls the API, then writes
 * the FRESH response the server just computed into `cart` -- this store
 * never computes or guesses a total itself. This is what makes a
 * cart-item-count badge elsewhere in the app (header, mobile nav, ...)
 * able to read from one shared source of truth instead of each
 * component fetching or computing its own copy.
 *
 * Not a second state-management system: this is the same Zustand
 * `create()` Phase 1 already established for useUIStore -- no new
 * library, no parallel architecture.
 */
const useCartStore = create((set, get) => ({
  cart: null, // shape: {id, items, item_count, subtotal, total} once loaded
  isLoading: false,
  error: null,

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

  async updateItem(itemId, quantity) {
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

  async removeItem(itemId) {
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

  async clear() {
    set({ isLoading: true, error: null });
    try {
      const cart = await cartApi.clearCart();
      set({ cart, isLoading: false });
    } catch (err) {
      set({ isLoading: false, error: normalizeApiError(err) });
    }
  },

  /**
   * Called on logout (see master spec step 17: "do not expose the
   * previous user's cart/wishlist to the next user"). No frontend
   * login/logout flow exists yet -- Phase 3 only built the backend
   * auth endpoints, and the actual login/logout UI is later frontend
   * work -- so this is exposed and ready, not yet wired to an event.
   * Whatever future login/logout handler is built should call
   * useCartStore.getState().reset() alongside the equivalent wishlist
   * reset.
   */
  reset() {
    set({ cart: null, isLoading: false, error: null });
  },

  /** Convenience selector -- reads the badge count without every
   * consumer needing to know cart can be null before it's first loaded. */
  getItemCount() {
    return get().cart?.item_count ?? 0;
  },
}));

export default useCartStore;
