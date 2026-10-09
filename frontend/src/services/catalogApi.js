import apiClient from "./apiClient";
import { fetchAllPages, fetchAllPagesAsEnvelope } from "./pagination";

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
  return fetchAllPagesAsEnvelope(() => apiClient.get("/categories/", { params }));
}

export function getCategory(slug) {
  return apiClient.get(`/categories/${slug}/`).then((res) => res.data);
}

export function getCategoryTree() {
  // The nested tree is still a collection endpoint: load every root page so
  // Header and Home never omit a category when the catalog grows.
  return fetchAllPages(() => apiClient.get("/categories/tree/"));
}

// --- Brands --------------------------------------------------------------------

export function listBrands(params = {}) {
  return fetchAllPagesAsEnvelope(() => apiClient.get("/brands/", { params }));
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
  // Shop, search and review surfaces intentionally control one page at a
  // time, so they retain DRF's pagination metadata.
  return apiClient.get("/products/", { params }).then((res) => res.data);
}

/**
 * Fetch every matching product page while retaining the familiar envelope.
 * This is for consumers that must resolve a complete finite id set (the
 * guest cart), rather than a visual pager or deliberately limited search.
 */
export function listAllProducts(params = {}) {
  return fetchAllPagesAsEnvelope(() => apiClient.get("/products/", { params }));
}

/**
 * Part R5 item 8: dynamic attribute facets (one checkbox group per
 * attribute) for the shop sidebar. Optionally narrowed by category:
 * { results: [{ slug, name, values: [{ value, count }] }] }.
 */
export function listFacets(params = {}) {
  return fetchAllPagesAsEnvelope(() => apiClient.get("/products/facets/", { params }));
}

export function getProduct(slug) {
  return apiClient.get(`/products/${slug}/`).then((res) => res.data);
}
