import { DEFAULT_CONTENT, normalizeContent } from "../content/defaults";
import apiClient from "./apiClient";

/**
 * Store-wide contact/branding settings (Part 1) -- one public endpoint,
 * cached in-module after the first successful fetch (the values change
 * only when the owner edits them in admin).
 */
let cache = null;

export function resetSiteSettingsCache() {
  cache = null;
}

export function fetchSiteSettings() {
  if (cache) return Promise.resolve(cache);
  return apiClient
    .get("/site/settings/")
    .then((res) => {
      cache = res.data || {};
      return cache;
    })
    .catch(() => ({}));
}

/**
 * Part R3: Iran's 31 provinces + main cities for the address selects.
 * Cached after the first successful fetch (the dataset ships with the
 * backend and only changes when the owner extends it).
 */
let locationsCache = null;

export function fetchLocations() {
  if (locationsCache) return Promise.resolve(locationsCache);
  return apiClient
    .get("/accounts/locations/")
    .then((res) => {
      locationsCache = res.data || { provinces: [] };
      return locationsCache;
    })
    .catch(() => ({ provinces: [] }));
}


/**
 * Owner-editable storefront content + theme (Task 1/2).
 *
 * One request per page load: the backend builds /site/content/ from a
 * cached payload (invalidated by a signal on every save), so calling this
 * from the header, the footer and a page costs a single HTTP call. The
 * promise is cached, not just the value, so simultaneous callers share it.
 *
 * Never rejects: the storefront must keep rendering today's texts when the
 * API is down (see content/defaults.js).
 */
let contentPromise = null;

export function fetchSiteContent({ force = false } = {}) {
  if (!force && contentPromise) return contentPromise;
  contentPromise = apiClient
    .get("/site/content/")
    .then((res) => normalizeContent(res.data))
    .catch(() => DEFAULT_CONTENT);
  return contentPromise;
}

/** Drop the in-module cache (tests, and after an owner-facing save). */
export function resetSiteContentCache() {
  contentPromise = null;
}

/**
 * One info page by slug: versioned `body` HTML the backend already
 * sanitised, plus SEO fields. Returns null for an unpublished/unknown page
 * (the API answers 404) -- the page then renders the storefront 404.
 */
export function fetchInfoPage(slug) {
  return apiClient
    .get(`/site/pages/${encodeURIComponent(slug)}/`)
    .then((res) => (res.data && res.data.body !== undefined ? res.data : null))
    .catch((error) => {
      if (error?.response?.status === 404) return null;
      throw error;
    });
}
