import apiClient from "./apiClient";

/**
 * Cart API service layer (Phase 5). Same pattern as catalogApi.js
 * (Phase 4) -- plain functions wrapping the shared apiClient, no new
 * Axios instance, nothing React-specific here. See hooks/useCartStore.js
 * for the stateful layer built on top of these.
 *
 * The backend is authoritative for pricing/totals -- none of these
 * functions ever send a price; only product/variant identifiers and
 * quantities. Every response already contains the freshly-computed
 * cart (items, item_count, subtotal, total), which is exactly what the
 * store below writes back into its state after each call.
 */

export function fetchCart() {
  return apiClient.get("/cart/").then((res) => res.data);
}

/**
 * @param {number} productId
 * @param {number|null} variantId
 * @param {number} quantity
 */
export function addCartItem(productId, variantId, quantity) {
  return apiClient
    .post("/cart/items/", { product_id: productId, variant_id: variantId ?? undefined, quantity })
    .then((res) => res.data);
}

/**
 * @param {number} itemId - the cart item id (not the product id)
 * @param {number} quantity - 0 removes the item, per the backend's own contract
 */
export function updateCartItem(itemId, quantity) {
  return apiClient.patch(`/cart/items/${itemId}/`, { quantity }).then((res) => res.data);
}

export function removeCartItem(itemId) {
  return apiClient.delete(`/cart/items/${itemId}/`).then((res) => res.data);
}

export function clearCart() {
  return apiClient.delete("/cart/").then((res) => res.data);
}
