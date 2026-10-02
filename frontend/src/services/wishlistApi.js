import apiClient from "./apiClient";

/**
 * Wishlist API service layer (Phase 5). Same pattern as cartApi.js and
 * catalogApi.js -- plain functions over the shared apiClient.
 *
 * Note: GET /wishlist/ returns a bare array, not a paginated
 * {count, next, previous, results} shape -- WishlistListView is a plain
 * APIView, not a paginated list endpoint (unlike the Phase 4 catalog
 * list endpoints). Callers should treat fetchWishlist()'s result as an
 * array directly.
 */

export function fetchWishlist() {
  return apiClient.get("/wishlist/").then((res) => res.data);
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
