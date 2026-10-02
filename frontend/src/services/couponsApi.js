import apiClient from "./apiClient";

/**
 * Coupons API service layer. The client only ever SENDS a code; the
 * server decides validity and the Toman amount (see backend
 * apps.discounts.services). validateCoupon() previews a code against the
 * caller's live cart; actual application happens inside checkout.
 */

export function validateCoupon(code) {
  return apiClient.post("/discounts/coupons/validate/", { code }).then((res) => res.data);
}
