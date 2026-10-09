import apiClient from "./apiClient";
import { fetchAllPages, fetchAllPagesAsEnvelope } from "./pagination";

/**
 * Banners / daily-deals API service layer (homepage content).
 */

export function fetchBanners() {
  // Home renders all active slides, not an arbitrary first API page.
  return fetchAllPages(() => apiClient.get("/banners/"));
}

export function fetchDailyDeals() {
  // `server_now` drives the countdown. The normalized envelope retains it
  // while loading every page of active deals.
  return fetchAllPagesAsEnvelope(() => apiClient.get("/banners/daily-deals/"));
}
