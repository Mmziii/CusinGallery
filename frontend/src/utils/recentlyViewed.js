/**
 * Part R5 item 10: browser-local "recently viewed" list.
 *
 * Deliberately trivial by spec: a localStorage array of product ids,
 * most recent first, capped at 12. NO server storage -- nothing here is
 * ever sent to the backend except as an ?ids= query when the widget
 * hydrates, and clearing your browser storage clears the list.
 */
export const RECENT_KEY = "cusin_recently_viewed";
export const RECENT_LIMIT = 12;

function read() {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    // Defensive: keep only positive integers (older/corrupt entries drop).
    return parsed.filter((id) => Number.isInteger(id) && id > 0);
  } catch {
    return []; // private mode / corrupt JSON -> behave as empty
  }
}

/** Record a product view: most recent first, deduplicated, capped at 12. */
export function recordView(productId) {
  if (!Number.isInteger(productId) || productId <= 0) return;
  try {
    const next = [productId, ...read().filter((id) => id !== productId)].slice(0, RECENT_LIMIT);
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // Storage full/unavailable: the feature silently no-ops.
  }
}

/** Current ids, most recent first (never throws). */
export function getRecentlyViewed() {
  return read();
}
