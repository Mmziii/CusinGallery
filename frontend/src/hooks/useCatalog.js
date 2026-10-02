import { getCategoryTree, getProduct, listCategories, listProducts } from "../services/catalogApi";
import { useAsync } from "./useAsync";

/**
 * @param {Object} params - see catalogApi.listProducts
 * @returns {{data: object|null, isLoading: boolean, error: Error|null}}
 *   `data` is the raw paginated response ({count, next, previous, results})
 *   when loaded -- not unwrapped, so callers keep access to pagination
 *   metadata without this hook inventing its own shape for it.
 */
export function useProducts(params = {}) {
  return useAsync(() => listProducts(params), [JSON.stringify(params)]);
}

/**
 * @param {string} slug
 */
export function useProduct(slug) {
  return useAsync(() => getProduct(slug), [slug]);
}

export function useCategories(params = {}) {
  return useAsync(() => listCategories(params), [JSON.stringify(params)]);
}

export function useCategoryTree() {
  return useAsync(() => getCategoryTree(), []);
}
