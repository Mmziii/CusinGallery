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
 * @param {Object} addressPayload - exactly one of two shapes:
 *   { address_id: number }  -- use one of the user's own saved addresses
 *   OR
 *   { recipient_name, phone, province, city, address, postal_code, unit?, building_number? }
 *     -- a one-off address, not saved to the account
 * @returns the created Order (see fetchOrder's return shape)
 */
export function checkout(addressPayload) {
  return apiClient.post("/orders/checkout/", addressPayload).then((res) => res.data);
}

/**
 * @param {Object} params - optional, e.g. {page: 2} for pagination
 * @returns {Promise<{count, next, previous, results}>} -- paginated,
 *   unlike wishlist's bare-array response; see OrderListView (a
 *   generics.ListAPIView, using the project's default PageNumberPagination).
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
