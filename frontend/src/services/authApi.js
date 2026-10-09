import apiClient from "./apiClient";
import { fetchAllPages } from "./pagination";

/**
 * Accounts/auth API service layer. Session-based (no JWT): login/register
 * set the httponly session cookie server-side; logout flushes it. All the
 * client ever does is POST credentials and read /me/.
 */

export function fetchMe() {
  return apiClient.get("/accounts/me/").then((res) => res.data);
}

export function register(payload) {
  // payload: { phone, password, password_confirm, email?, first_name?, last_name? }
  return apiClient.post("/accounts/register/", payload).then((res) => res.data);
}

export function login(payload) {
  // payload: { identifier (phone or email), password }
  return apiClient.post("/accounts/login/", payload).then((res) => res.data);
}

export function logout() {
  return apiClient.post("/accounts/logout/").then((res) => res.data);
}

export function updateProfile(patch) {
  return apiClient.patch("/accounts/me/", patch).then((res) => res.data);
}

export function changePassword(payload) {
  return apiClient.post("/accounts/me/change-password/", payload).then((res) => res.data);
}

export function requestPasswordReset(identifier) {
  return apiClient.post("/accounts/password-reset/", { identifier }).then((res) => res.data);
}

export function confirmPasswordReset(payload) {
  // Link mode (emailed link):        { uid, token, new_password, new_password_confirm }
  // Code mode (phone-only accounts): { phone, code, new_password, new_password_confirm }
  return apiClient.post("/accounts/password-reset/confirm/", payload).then((res) => res.data);
}

// --- Addresses ---------------------------------------------------------------

/**
 * All saved addresses as a plain array. The API is paginated, and this
 * follows every `next` page so address selection never silently omits an
 * older address.
 */
export function listAddresses() {
  return fetchAllPages(() => apiClient.get("/accounts/addresses/"));
}

export function createAddress(payload) {
  return apiClient.post("/accounts/addresses/", payload).then((res) => res.data);
}

export function updateAddress(id, patch) {
  return apiClient.patch(`/accounts/addresses/${id}/`, patch).then((res) => res.data);
}

export function deleteAddress(id) {
  return apiClient.delete(`/accounts/addresses/${id}/`).then((res) => res.data);
}

export function setDefaultAddress(id) {
  return apiClient.post(`/accounts/addresses/${id}/set-default/`).then((res) => res.data);
}
