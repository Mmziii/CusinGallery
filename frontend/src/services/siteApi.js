import apiClient from "./apiClient";

/**
 * Store-wide contact/branding settings (Part 1) -- one public endpoint,
 * cached in-module after the first successful fetch (the values change
 * only when the owner edits them in admin).
 */
let cache = null;

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
