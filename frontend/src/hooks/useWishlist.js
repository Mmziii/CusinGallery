import { useCallback, useEffect, useState } from "react";

import * as wishlistApi from "../services/wishlistApi";
import { normalizeApiError } from "../utils/apiError";

/**
 * Wishlist hooks (Phase 5).
 *
 * Deliberately a plain hook, not a Zustand store like useCartStore --
 * per the instruction to "avoid unnecessary global state": a cart badge
 * needs to be readable from many places in the app at once (header,
 * mobile nav, ...), which is exactly what Zustand is for. Wishlist
 * status is naturally checked per-product (see useWishlistStatus below,
 * built on the dedicated GET /wishlist/check/ endpoint) rather than
 * needing one global list kept in sync everywhere -- a plain
 * component-local hook is the right amount of state management here,
 * not a second global store for its own sake.
 */

/**
 * The full wishlist -- for an actual "My Wishlist" page.
 * @returns {{items: Array, isLoading: boolean, error: object|null,
 *   addItem: (productId: number) => Promise<{success: boolean}>,
 *   removeItem: (itemId: number) => Promise<{success: boolean}>,
 *   refetch: () => void}}
 */
export function useWishlist() {
  const [items, setItems] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const refetch = useCallback(() => {
    setIsLoading(true);
    setError(null);
    wishlistApi
      .fetchWishlist()
      .then((data) => setItems(data))
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const addItem = useCallback(async (productId) => {
    try {
      await wishlistApi.addWishlistItem(productId);
      refetch();
      return { success: true };
    } catch (err) {
      const normalized = normalizeApiError(err);
      setError(normalized);
      return { success: false, error: normalized };
    }
  }, [refetch]);

  const removeItem = useCallback(async (itemId) => {
    try {
      await wishlistApi.removeWishlistItem(itemId);
      setItems((current) => current.filter((item) => item.id !== itemId));
      return { success: true };
    } catch (err) {
      const normalized = normalizeApiError(err);
      setError(normalized);
      return { success: false, error: normalized };
    }
  }, []);

  return { items, isLoading, error, addItem, removeItem, refetch };
}

/**
 * Lightweight "is this one product wishlisted" check, for a heart icon
 * on a product card/detail page -- uses GET /wishlist/check/ rather than
 * fetching the entire wishlist just to answer one boolean.
 * @param {number} productId
 */
export function useWishlistStatus(productId) {
  const [isWishlisted, setIsWishlisted] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!productId) return;
    let cancelled = false;
    setIsLoading(true);
    wishlistApi
      .checkWishlisted(productId)
      .then((result) => {
        if (!cancelled) setIsWishlisted(result);
      })
      .catch((err) => {
        if (!cancelled) setError(normalizeApiError(err));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [productId]);

  const toggle = useCallback(async () => {
    try {
      if (isWishlisted) {
        // Note: toggling off requires the wishlist ITEM id, which this
        // hook doesn't have (only a boolean status) -- callers needing
        // full remove functionality should use useWishlist() instead.
        // This toggle only supports the add direction cleanly; kept
        // simple rather than over-fetching just to support removal from
        // a component that only ever asked "is this wishlisted".
        return { success: false, error: { message: "Use useWishlist().removeItem to un-wishlist." } };
      }
      await wishlistApi.addWishlistItem(productId);
      setIsWishlisted(true);
      return { success: true };
    } catch (err) {
      const normalized = normalizeApiError(err);
      setError(normalized);
      return { success: false, error: normalized };
    }
  }, [isWishlisted, productId]);

  return { isWishlisted, isLoading, error, toggle };
}
