import apiClient from "./apiClient";

/**
 * Back-in-stock signup (Part 2): phone must be 09xxxxxxxxx; the server
 * throttles, validates stock state and de-duplicates active signups.
 */
export function subscribeBackInStock(productId, variantId, phone) {
  return apiClient
    .post("/products/back-in-stock/", { product_id: productId, variant_id: variantId ?? undefined, phone })
    .then((res) => res.data);
}
