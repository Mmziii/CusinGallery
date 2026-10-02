import { create } from "zustand";

/**
 * Foundation-only UI state store (things like "is the cart drawer open"
 * or "is the mobile menu open") -- purely client-side, ephemeral state
 * that has no business meaning and should never be treated as a source
 * of truth for cart/order/user data.
 *
 * The actual cart, wishlist, and auth state are server-backed (per the
 * master spec) and will get their own store modules in Phase 5/Phase 3
 * that call the API via src/services/*, rather than holding authoritative
 * data client-side. This file exists now only to establish that pattern
 * and prove the store wiring works.
 */
const useUIStore = create((set) => ({
  isCartDrawerOpen: false,
  isMobileMenuOpen: false,

  openCartDrawer: () => set({ isCartDrawerOpen: true }),
  closeCartDrawer: () => set({ isCartDrawerOpen: false }),
  toggleMobileMenu: () =>
    set((state) => ({ isMobileMenuOpen: !state.isMobileMenuOpen })),
}));

export default useUIStore;
