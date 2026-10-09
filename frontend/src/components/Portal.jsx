import PropTypes from "prop-types";
import { useState } from "react";
import { createPortal } from "react-dom";

/**
 * Renders children into document.body instead of their position in the
 * React tree.
 *
 * Why this exists: the full-viewport drawers (`.minicart`,
 * `.site-header__drawer`) originate from Header.jsx. Rendering fixed UI
 * inside an application shell is fragile: a future filter, transform or
 * containment on any shell ancestor can turn that ancestor into the fixed
 * containing block and collapse `inset: 0` to its box. The compact header's
 * blur now lives on a child pseudo-element specifically to avoid that too,
 * but portaling the drawers to document.body is the durable structural
 * boundary: their fixed inset remains the viewport in every scroll state.
 *
 * The focus trap, Escape handling and focus restore are unaffected: they
 * work off a ref to the rendered DOM node, not off the React tree position.
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
