import PropTypes from "prop-types";
import { useState } from "react";
import { createPortal } from "react-dom";

/**
 * Renders children into document.body instead of their position in the
 * React tree.
 *
 * Why this exists (Part S5 follow-up 4): the full-viewport drawers
 * (`.minicart`, `.site-header__drawer`) are rendered from Header.jsx, so
 * their DOM position is inside `<header class="site-header">`. That is
 * harmless while the page is at the top, but as soon as it is scrolled the
 * header gets the `.site-header--compact` class, which applies
 * `backdrop-filter: blur(12px)`. Per the filter-effects spec an element
 * with a filter/backdrop-filter becomes the CONTAINING BLOCK for its fixed
 * descendants, so `position: fixed; inset: 0` stopped meaning "the
 * viewport" and started meaning "the header's padding box" -- the drawer
 * collapsed to the header's height (about 60-76px), its content overflowed
 * and the checkout button spilled out of the panel. Portaling the drawers
 * to document.body keeps them out of any filtered/transformed ancestor, so
 * `inset: 0` is the viewport again in every scroll state.
 *
 * The focus trap, Escape handling and focus restore are unaffected: they
 * work off a ref to the rendered DOM node, not off the React tree
 * position.
 */
function Portal({ children }) {
  // document.body is available on the very first client render, so the
  // portal mounts in the SAME commit as the drawer state change -- one
  // extra render would leave the drawer's ref empty for a paint, which the
  // focus trap (and any measurement) would have to work around.
  const [host] = useState(() => (typeof document === "undefined" ? null : document.body));

  if (!host) return null;
  return createPortal(children, host);
}

Portal.propTypes = {
  children: PropTypes.node,
};

export default Portal;
