import PropTypes from "prop-types";

import Icon from "./Icon";

/**
 * SVG star rating (Part R2): stars are icons, never text glyphs.
 * `rating` may be fractional -- full stars fill, a half star clips.
 */
function StarRating({ rating = 0, size = 16, className = "" }) {
  const value = Math.max(0, Math.min(5, Number(rating) || 0));
  return (
    <span
      className={`stars ${className}`.trim()}
      role="img"
      aria-label={`${value} ستاره از ۵`}
    >
      {[1, 2, 3, 4, 5].map((n) => {
        const fill = Math.max(0, Math.min(1, value - (n - 1)));
        return (
          <span key={n} className="stars__star" style={{ "--fill": `${fill * 100}%` }}>
            <Icon name="star" size={size} className="stars__base" />
            <span className="stars__fill" aria-hidden="true">
              <Icon name="star" size={size} filled />
            </span>
          </span>
        );
      })}
    </span>
  );
}

StarRating.propTypes = {
  rating: PropTypes.number,
  size: PropTypes.number,
  className: PropTypes.string,
};

export default StarRating;
