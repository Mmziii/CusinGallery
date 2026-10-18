/**
 * Part R5 item 10: browser-local "recently viewed" list.
 *
 * Deliberately trivial by spec: a localStorage array of product ids,
 * most recent first. Ten previous products are shown. NO server storage -- nothing here is
 * ever sent to the backend except as an ?ids= query when the widget
 * hydrates, and clearing your browser storage clears the list.
 */
export const RECENT_KEY = "cusin_recently_viewed";
export const RECENT_LIMIT = 10;
// Reserve one slot for the current product. After a reload the PDP can
// still exclude itself and show TEN predecessors, not just nine.
const STORAGE_LIMIT = RECENT_LIMIT + 1;

function read() {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    // Defensive: keep only positive integers (older/corrupt entries drop).
    return [...new Set(parsed.filter((id) => Number.isInteger(id) && id > 0))].slice(0, STORAGE_LIMIT);
  } catch {
    return []; // private mode / corrupt JSON -> behave as empty
  }
}

/** Record a product view: most recent first, deduplicated, bounded to the current product plus ten predecessors. */
export function recordView(productId) {
  if (!Number.isInteger(productId) || productId <= 0) return;
  try {
    const next = [productId, ...read().filter((id) => id !== productId)].slice(0, STORAGE_LIMIT);
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // Storage full/unavailable: the feature silently no-ops.
  }
}

/** Current ids, most recent first (never throws). */
export function getRecentlyViewed(excludeId = null) {
  return read().filter((id) => id !== excludeId).slice(0, RECENT_LIMIT);
}
