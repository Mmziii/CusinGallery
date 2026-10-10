import apiClient from "./apiClient";
import { fetchAllPages } from "./pagination";

/**
 * Wishlist API service layer (Phase 5). Same pattern as cartApi.js and
 * catalogApi.js -- plain functions over the shared apiClient.
 *
 * GET /wishlist/ uses the same paginated envelope as every storefront
 * collection. This service unwraps it and follows `next`, so callers work
 * with the complete plain array (and remain safe during a rolling deploy
 * against an older bare-array server).
 */

export function fetchWishlist() {
  return fetchAllPages(() => apiClient.get("/wishlist/"));
}

/**
 * @param {number} productId
 * @returns the created (or already-existing) wishlist item -- adding an
 *   already-wishlisted product is not an error (see backend docs), it
 *   just returns the existing entry.
 */
export function addWishlistItem(productId) {
  return apiClient.post("/wishlist/items/", { product_id: productId }).then((res) => res.data);
}

/**
 * @param {number} itemId - the wishlist item id (not the product id)
 */
export function removeWishlistItem(itemId) {
  return apiClient.delete(`/wishlist/items/${itemId}/`);
}

/**
 * @param {number} productId
 * @returns {Promise<boolean>}
 */
export function checkWishlisted(productId) {
  return apiClient
    .get("/wishlist/check/", { params: { product: productId } })
    .then((res) => res.data.is_wishlisted);
}
