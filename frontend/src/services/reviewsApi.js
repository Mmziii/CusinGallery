import apiClient from "./apiClient";
import { fetchAllPages } from "./pagination";

/**
 * Reviews API service layer.
 */

export function fetchProductReviews(productId, params = {}) {
  return apiClient.get(`/reviews/product/${productId}/`, { params }).then((res) => res.data);
}

export function fetchProductReviewSummary(productId) {
  return apiClient.get(`/reviews/product/${productId}/summary/`).then((res) => res.data);
}

export function createReview(payload) {
  // payload: { product_id, rating, title?, body? }
  return apiClient.post("/reviews/", payload).then((res) => res.data);
}

/** All of the current customer's reviews as a plain array. */
export function fetchMyReviews() {
  return fetchAllPages(() => apiClient.get("/reviews/mine/"));
}

export function updateReview(id, patch) {
  return apiClient.patch(`/reviews/${id}/`, patch).then((res) => res.data);
}

export function deleteReview(id) {
  return apiClient.delete(`/reviews/${id}/`).then((res) => res.data);
}
