import { create } from "zustand";
import * as api from "../services/wishlistApi";
import { normalizeApiError } from "../utils/apiError";
import { trackEvent } from "../utils/behaviour";
import { toast } from "../utils/toast";
let pending;
let generation = 0;
const useWishlistStore = create((set, get) => ({
  items: [], isLoading: true, error: null, revision: 0,
  reset: () => { generation += 1; pending = null; set({ items: [], isLoading: false, error: null }); },
  refetch: () => {
    if (pending) return pending;
    const current = generation;
    set({ isLoading: true, error: null });
    pending = api.fetchWishlist().then(items => { if (current === generation) set({ items, isLoading: false }); })
      .catch(error => { if (current === generation) set({ error: normalizeApiError(error), isLoading: false }); })
      .finally(() => { if (current === generation) pending = null; });
    return pending;
  },
  async toggle(productId) {
    const existing = get().items.find(item => item.product.id === productId);
    try {
      if (existing) await api.removeWishlistItem(existing.id);
      else {
        const item = await api.addWishlistItem(productId);
        trackEvent("wishlist_add", { product_id: productId });
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
