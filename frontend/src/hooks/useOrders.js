import { useCallback, useState } from "react";

import * as orderApi from "../services/orderApi";
import useCartStore from "../store/useCartStore";
import { normalizeApiError } from "../utils/apiError";
import { useAsync } from "./useAsync";

/**
 * Order/checkout hooks (Phase 6).
 *
 * useOrders/useOrder are plain read hooks (useAsync), same pattern as
 * useCatalog.js -- order history doesn't need cross-cutting global state
 * the way the cart badge does, so there's no new store for it, per the
 * same "avoid unnecessary global state" reasoning applied to wishlist in
 * Phase 5.
 *
 * useCheckout is the one piece that DOES touch existing global state:
 * after a successful checkout, the backend has already cleared the
 * user's cart (see apps.orders.services.checkout) -- so this calls
 * useCartStore's own fetchCart() afterward to pull that fresh,
 * now-empty cart into the existing cart store, rather than leaving it
 * showing stale contents or duplicating cart-clearing logic here.
 */

/**
 * @param {Object} params - e.g. {page: 2}
 * @returns {{data: {count,next,previous,results}|null, isLoading, error}}
 */
export function useOrders(params = {}) {
  return useAsync(() => orderApi.fetchOrders(params), [JSON.stringify(params)]);
}

/**
 * @param {number} orderId
 */
export function useOrder(orderId) {
  return useAsync(() => orderApi.fetchOrder(orderId), [orderId]);
}

/**
 * @returns {{submit: (addressPayload: object) => Promise<{success: boolean, order?: object, error?: object}>,
 *   isSubmitting: boolean, error: object|null}}
 */
export function useCheckout() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const submit = useCallback(async (addressPayload) => {
    setIsSubmitting(true);
    setError(null);
    try {
      const order = await orderApi.checkout(addressPayload);
      // Reflects the server-side cart-clearing that just happened as
      // part of a successful checkout (apps.orders.services.checkout)
      // -- fetches the fresh (now empty) cart rather than assuming its
      // new shape or clearing it locally without confirming with the
      // server.
      useCartStore.getState().fetchCart();
      setIsSubmitting(false);
      return { success: true, order };
    } catch (err) {
      const normalized = normalizeApiError(err);
      setError(normalized);
      setIsSubmitting(false);
      return { success: false, error: normalized };
    }
  }, []);

  return { submit, isSubmitting, error };
}
