import apiClient from "./apiClient";

/**
 * Order/checkout API service layer (Phase 6). Same pattern as
 * cartApi.js/wishlistApi.js/catalogApi.js -- plain functions over the
 * shared apiClient, verified field-for-field against the actual backend
 * serializers (apps/orders/serializers.py) rather than assumed.
 *
 * The backend is authoritative for every price/shipping/total value --
 * none of these functions ever send one; checkout() only ever sends an
 * address selection.
 */

/**
 * @param {Object} payload - exactly one of two address shapes:
 *   { address_id: number }  -- use one of the user's own saved addresses
 *   OR
 *   { recipient_name, phone, province, city, address, postal_code, unit?, building_number? }
 *     -- a one-off address, not saved to the account
 *   Plus optionally:
 *   { shipping_method?: string }  -- one of fetchShippingMethods()' ids
 *     (omitted/blank = the default method); the COST and delivery window
 *     for it are always computed server-side, never sent from here.
 *   { coupon_code?: string }
 * @returns the created Order (see fetchOrder's return shape)
 */
export function checkout(payload) {
  return apiClient.post("/orders/checkout/", payload).then((res) => res.data);
}

/**
 * The selectable shipping methods and their current cost/delivery-window
 * configuration (GET /orders/shipping-methods/). The checkout page
 * renders its delivery selector from this -- shipping numbers are never
 * hardcoded in frontend code.
 * @returns {Promise<{default: string, methods: Array<{id, cost, free_threshold, min_days, max_days}>}>}
 */
export function fetchShippingMethods() {
  return apiClient.get("/orders/shipping-methods/").then((res) => res.data);
}

/**
 * @param {Object} params - optional, e.g. {page: 2} for pagination
 * @returns {Promise<{count, next, previous, results}>} -- one server page,
 *   used directly by the order-history pager. Wishlist intentionally exposes
 *   a complete plain array through its own service because its UI has no
 *   pager; both endpoints use the same DRF response envelope on the wire.
 */
export function fetchOrders(params = {}) {
  return apiClient.get("/orders/", { params }).then((res) => res.data);
}

/**
 * @param {number} orderId
 */
export function fetchOrder(orderId) {
  return apiClient.get(`/orders/${orderId}/`).then((res) => res.data);
}
