/**
 * The expanded phone header's border-box height -- the ONE number the
 * fixed phone header contributes to the document (through the spacer in
 * Header.jsx) and to `--site-header-height`.
 *
 * `getBoundingClientRect().height` is the border-box height: content +
 * padding + border. It is the only honest read here.
 *  - `scrollHeight` reports the CONTENT height and misses the box's
 *    padding/border, so a spacer sized from it is always a few px short
 *    (live PR 20: 232 measured where the bar really needed 246);
 *  - `offsetHeight` is also border-box, but on a height-LOCKED box it
 *    returns the lock itself, which is how the old pinned
 *    `--header-natural-height` re-measured itself forever at 190px while
 *    the search row spilled 41px below the bar.
 * The expanded inner is `height: auto` now, so the rect always describes
 * the real content. jsdom / hidden tabs report a 0 rect; fall back to
 * `offsetHeight` (also border-box) and finally to 0, which callers treat
 * as "no measurement yet" and never publish.
 */
export function measureBorderBoxHeight(element) {
  if (!element) return 0;
  const rectHeight =
    typeof element.getBoundingClientRect === "function"
      ? element.getBoundingClientRect().height || 0
      : 0;
  if (rectHeight > 0) return Math.round(rectHeight);
  return Math.round(element.offsetHeight || 0);
}
