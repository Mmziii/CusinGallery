import apiClient from "./apiClient";

/**
 * The Django REST Framework list envelope used by storefront collection
 * endpoints. Transitional bare arrays are deliberately accepted too: this
 * lets a deployed frontend talk safely to an older server during a rolling
 * deployment, while the backend contract test keeps new releases on the
 * standard shape.
 */
export function listResults(payload) {
  if (Array.isArray(payload)) return payload;
  return Array.isArray(payload?.results) ? payload.results : [];
}

export function isPaginatedList(payload) {
  return Boolean(
    payload &&
      !Array.isArray(payload) &&
      Array.isArray(payload.results) &&
      Object.prototype.hasOwnProperty.call(payload, "next")
  );
}

function responseData(response) {
  return response?.data ?? response;
}

async function collectPages(firstResponse) {
  let page = responseData(firstResponse);
  const first = page;
  const results = [...listResults(page)];
  const seenNextUrls = new Set();

  // DRF returns an absolute `next` URL by default. Axios accepts both that
  // form and a relative one, preserving the same session/CSRF configuration
  // held by apiClient for every follow-up request.
  while (isPaginatedList(page) && page.next) {
    const next = String(page.next);
    if (seenNextUrls.has(next)) {
      throw new Error("پاسخ صفحه‌بندی حلقه دارد.");
    }
    seenNextUrls.add(next);

    page = responseData(await apiClient.get(next));
    results.push(...listResults(page));
  }

  return { first, results };
}

/**
 * Fetch every page of a list endpoint and return only a plain array. Use it
 * where the UI needs to search/select across the whole customer-owned list
 * (addresses, wishlist and the customer's reviews).
 */
export async function fetchAllPages(request) {
  const { results } = await collectPages(await request());
  return results;
}

/**
 * Fetch every page but preserve the DRF envelope. Filter inputs and feature
 * rows need `results`, while the envelope keeps their contract explicit.
 */
export async function fetchAllPagesAsEnvelope(request) {
  const { first, results } = await collectPages(await request());
  const base = first && !Array.isArray(first) ? first : {};
  return {
    ...base,
    count: Number.isInteger(base.count) ? base.count : results.length,
    next: null,
    previous: null,
    results,
  };
}
