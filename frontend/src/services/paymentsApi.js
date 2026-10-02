import apiClient from "./apiClient";

/**
 * Payments API service layer (Phase 7). initiate() returns a
 * gateway redirect_url the browser must be sent to; the gateway then
 * bounces the browser back through the backend callback, which finally
 * redirects to the frontend /payment/result/ page.
 */

export function initiatePayment(orderId) {
  return apiClient.post("/payments/initiate/", { order_id: orderId }).then((res) => res.data);
}

export function fetchPayment(paymentId) {
  return apiClient.get(`/payments/${paymentId}/`).then((res) => res.data);
}
