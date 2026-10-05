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
