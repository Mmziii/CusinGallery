import { create } from "zustand";

import * as authApi from "../services/authApi";
import { normalizeApiError } from "../utils/apiError";
import useCartStore from "./useCartStore";

/**
 * Auth state store. Session-backed (httponly cookie on the server), so
 * this store only mirrors "who am I right now" from GET /accounts/me/
 * and the login/register responses -- it never holds a token.
 *
 * On login/register success and on logout it resets the cart store so the
 * previous user's cart is never shown to the next user (and vice versa),
 * per the spec's "don't leak one user's cart to another" rule.
 */
const useAuthStore = create((set) => ({
  user: null,
  isLoading: true, // true until the first /me/ probe resolves
  isAuthenticated: false,
  error: null,

  async fetchMe() {
    try {
      const user = await authApi.fetchMe();
      set({ user, isAuthenticated: true, isLoading: false, error: null });
      return { success: true };
    } catch (err) {
      // 401/403 just means "not logged in" -- not an error to surface.
      set({ user: null, isAuthenticated: false, isLoading: false, error: null });
      return { success: false };
    }
  },

  async login(identifier, password) {
    set({ isLoading: true, error: null });
    try {
      const user = await authApi.login({ identifier, password });
      set({ user, isAuthenticated: true, isLoading: false, error: null });
      useCartStore.getState().reset();
      return { success: true };
    } catch (err) {
      const normalized = normalizeApiError(err);
      set({ isLoading: false, error: normalized });
      return { success: false, error: normalized };
    }
  },

  async register(payload) {
    set({ isLoading: true, error: null });
    try {
      const user = await authApi.register(payload);
      set({ user, isAuthenticated: true, isLoading: false, error: null });
      useCartStore.getState().reset();
      return { success: true };
    } catch (err) {
      const normalized = normalizeApiError(err);
      set({ isLoading: false, error: normalized });
      return { success: false, error: normalized };
    }
  },

  async logout() {
    try {
      await authApi.logout();
    } finally {
      set({ user: null, isAuthenticated: false, isLoading: false, error: null });
      useCartStore.getState().reset();
    }
  },

  async updateProfile(patch) {
    try {
      const user = await authApi.updateProfile(patch);
      set({ user, error: null });
      return { success: true };
    } catch (err) {
      const normalized = normalizeApiError(err);
      set({ error: normalized });
      return { success: false, error: normalized };
    }
  },

  clearError() {
    set({ error: null });
  },
}));

export default useAuthStore;
