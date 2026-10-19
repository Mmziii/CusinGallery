import PropTypes from "prop-types";

/**
 * Minimal inline SVG icon set (Part R2): thin line icons, 1.5 stroke,
 * currentColor, no dependency. Replaces every emoji / Unicode pictograph
 * previously used in the UI (no Google-style emoji anywhere). A handwritten
 * set was chosen over lucide-react to keep the bundle and the dependency
 * list minimal -- the storefront needs exactly these glyphs.
 */
const PATHS = {
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </>
  ),
  close: <path d="M6 6l12 12M18 6L6 18" />,
  "chevron-down": <path d="m6 9 6 6 6-6" />,
  "arrow-up": <path d="M12 19V5m0 0-6 6m6-6 6 6" />,
  "chevron-left": <path d="m14 6-6 6 6 6" />,
  "chevron-right": <path d="m10 6 6 6-6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  check: <path d="m5 13 4 4L19 7" />,
  undo: <path d="M9 14 4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3" />,
  box: (
    <>
      <path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z" />
      <path d="M3 7.5 12 12l9-4.5M12 12v9" />
    </>
  ),
  truck: (
    <>
      <path d="M2 5h12v11H2zM14 9h4l4 4v3h-8z" />
      <circle cx="6.5" cy="18.5" r="1.8" />
      <circle cx="17.5" cy="18.5" r="1.8" />
    </>
  ),
  lock: (
    <>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </>
  ),
  phone: (
    <path d="M5 4h4l1.5 4.5L8 10a12 12 0 0 0 6 6l1.5-2.5L20 15v4a1.5 1.5 0 0 1-1.7 1.5A16.5 16.5 0 0 1 3.5 5.7 1.5 1.5 0 0 1 5 4z" />
  ),
  send: <path d="m21 3-9 18-3-8-8-3z M21 3 9 13" />,
  chat: (
    <>
      <path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z" />
      <path d="M9 11h.5M13 11h.5" />
    </>
  ),
  star: (
    <path d="m12 3.5 2.6 5.4 5.9.8-4.3 4.1 1.1 5.8L12 16.8l-5.3 2.8 1.1-5.8-4.3-4.1 5.9-.8z" />
  ),
  heart: (
    <path d="M12 20s-7.2-4.6-9.1-9A5.2 5.2 0 0 1 12 6.6 5.2 5.2 0 0 1 21.1 11c-1.9 4.4-9.1 9-9.1 9z" />
  ),
  alert: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5V13M12 16.5v.01" />
    </>
  ),
  bag: (
    <>
      <path d="M5 8h14l-1 12H6z" />
      <path d="M9 8a3 3 0 0 1 6 0" />
    </>
  ),
  // Mobile quick add-to-cart (Audit 19 item 1): a bag/cart with a plus sign.
  "cart-plus": (
    <>
      <path d="M4 7h2.2l1.9 9.5h9.7L20 9.5H7" />
      <circle cx="9.5" cy="20" r="1.2" />
      <circle cx="17" cy="20" r="1.2" />
      <path d="M15.5 2.5v4M13.5 4.5h4" />
    </>
  ),
  // Password visibility toggle (Audit 19 item 3).
  eye: (
    <>
      <path d="M2.5 12S6 5.8 12 5.8 21.5 12 21.5 12 18 18.2 12 18.2 2.5 12 2.5 12z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  "eye-off": (
    <>
      <path d="M4 4.5l15.5 15.5" />
      <path d="M9.6 6.3A9.7 9.7 0 0 1 12 5.8c6 0 9.5 6.2 9.5 6.2a17 17 0 0 1-3 3.6" />
      <path d="M6.3 8A17 17 0 0 0 2.5 12S6 18.2 12 18.2a9.6 9.6 0 0 0 3.4-.6" />
      <path d="M10 10.2a3 3 0 0 0 4.1 4.1" />
    </>
  ),
  // Delivery-method cards at checkout (Audit 19 item 2).
  store: (
    <>
      <path d="M4 9.5V20h16V9.5" />
      <path d="M3 4h18l1 5.5a3 3 0 0 1-6 0 3 3 0 0 1-6 0 3 3 0 0 1-6 0z" />
      <path d="M10 20v-5h4v5" />
    </>
  ),
  "bolt-fast": <path d="M13 2 4.5 13.5H11l-1 8.5L19 10.5h-6.5z" />,
  // Social channels (footer + floating contact, Task 3). Instagram is a
  // rounded square with the camera lens and flash; the others reuse the
  // existing send/chat/phone glyphs.
  instagram: (
    <>
      <rect x="3.5" y="3.5" width="17" height="17" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.2" cy="6.8" r="0.6" />
    </>
  ),
  // Stage 2/3: hamburger menu, category tiles, account surfaces.
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  home: (
    <>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.8V21h14V9.8" />
      <path d="M10 21v-6h4v6" />
    </>
  ),
  grid: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <path d="M12 7.5v.01" />
    </>
  ),
  logout: (
    <>
      <path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4" />
      <path d="m10 8-4 4 4 4" />
      <path d="M6 12h10" />
    </>
  ),
  // Stage 4: authenticity guarantee.
  "shield-check": (
    <>
      <path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" />
      <path d="m9 11.5 2 2 4-4" />
    </>
  ),
  // Stage 5: countdown / express delivery.
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
};

function Icon({ name, size = 20, filled = false, className = "" }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`icon ${className}`.trim()}
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name] || null}
    </svg>
  );
}

Icon.propTypes = {
  name: PropTypes.oneOf(Object.keys(PATHS)).isRequired,
  size: PropTypes.number,
  filled: PropTypes.bool,
  className: PropTypes.string,
};

export default Icon;
