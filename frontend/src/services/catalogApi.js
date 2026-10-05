import apiClient from "./apiClient";

/**
 * Catalog API service layer (Phase 4). Every catalog-related HTTP call
 * goes through these functions instead of components calling apiClient
 * directly -- this is the reusable data-layer integration the phase
 * asks for, deliberately stopping short of building the actual
 * storefront UI (pages/components) on top of it; that's later-phase
 * frontend work.
 *
 * All functions return the parsed response body (response.data) via a
 * plain Promise -- callers (hooks, or components directly) handle
 * loading/error state themselves. Nothing here assumes React.
 */

// --- Categories ---------------------------------------------------------------

export function listCategories(params = {}) {
  return apiClient.get("/categories/", { params }).then((res) => res.data);
}

export function getCategory(slug) {
  return apiClient.get(`/categories/${slug}/`).then((res) => res.data);
}

export function getCategoryTree() {
  return apiClient.get("/categories/tree/").then((res) => res.data);
}

// --- Brands --------------------------------------------------------------------

export function listBrands(params = {}) {
  return apiClient.get("/brands/", { params }).then((res) => res.data);
}

export function getBrand(slug) {
  return apiClient.get(`/brands/${slug}/`).then((res) => res.data);
}

// --- Products --------------------------------------------------------------------

/**
 * @param {Object} params - any combination of the backend's supported
 *   query params (see README's "Phase 4 catalog API" section):
 *   category, brand, min_price, max_price, in_stock, is_featured,
 *   is_new, is_best_seller, search, ordering (newest|oldest|price_asc|price_desc), page
 */
export function listProducts(params = {}) {
  return apiClient.get("/products/", { params }).then((res) => res.data);
}

/**
 * Part R5 item 8: dynamic attribute facets (one checkbox group per
 * attribute) for the shop sidebar. Optionally narrowed by category:
 * { results: [{ slug, name, values: [{ value, count }] }] }.
 */
export function listFacets(params = {}) {
  return apiClient.get("/products/facets/", { params }).then((res) => res.data);
}

export function getProduct(slug) {
  return apiClient.get(`/products/${slug}/`).then((res) => res.data);
}
