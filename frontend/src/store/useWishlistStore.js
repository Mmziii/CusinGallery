import { create } from "zustand";
import * as api from "../services/wishlistApi";
import { normalizeApiError } from "../utils/apiError";
import { toast } from "../utils/toast";
let pending;
const useWishlistStore = create((set, get) => ({
  items: [], isLoading: true, error: null, revision: 0,
  reset: () => set({ items: [], isLoading: false, error: null }),
  refetch: () => {
    if (pending) return pending;
    set({ isLoading: true, error: null });
    pending = api.fetchWishlist().then(items => set({ items, isLoading: false }))
      .catch(error => set({ error: normalizeApiError(error), isLoading: false }))
      .finally(() => { pending = null; });
    return pending;
  },
  async toggle(productId) {
    const existing = get().items.find(item => item.product.id === productId);
    try {
      if (existing) await api.removeWishlistItem(existing.id);
      else {
        const item = await api.addWishlistItem(productId);
        set(state => ({ items: [...state.items.filter(row => row.product.id !== productId), item], revision: state.revision + 1 }));
      }
      if (existing) set(state => ({ items: state.items.filter(item => item.id !== existing.id), revision: state.revision + 1 }));
      toast(existing ? "از علاقه‌مندی‌ها حذف شد" : "به علاقه‌مندی‌ها اضافه شد", "success");
      return { success: true };
    } catch (err) {
      const error = normalizeApiError(err);
      toast(error.message, "error");
      return { success: false, error };
    }
  },
}));
export default useWishlistStore;
