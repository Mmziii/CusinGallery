import apiClient from "./apiClient";

/**
 * Banners / daily-deals API service layer (homepage content).
 */

export function fetchBanners() {
  // Returns a bare array (unpaginated) of active banners.
  return apiClient.get("/banners/").then((res) => res.data);
}

export function fetchDailyDeals() {
  // Returns { server_now, results: [...] } -- server_now drives the
  // countdown so it doesn't depend on the client's clock.
  return apiClient.get("/banners/daily-deals/").then((res) => res.data);
}
