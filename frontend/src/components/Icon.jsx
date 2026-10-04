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
