import PropTypes from "prop-types";

/**
 * Skeleton loaders (Part 3) replace spinners for content areas. Pure
 * CSS shimmer; respects prefers-reduced-motion (static tint instead).
 */
export function ProductCardSkeleton() {
  return (
    <div className="product-card product-card--skeleton" aria-hidden="true">
      <div className="skeleton product-card__image" />
      <div className="skeleton skeleton--line" style={{ width: "70%" }} />
      <div className="skeleton skeleton--line" style={{ width: "40%" }} />
    </div>
  );
}

export function CardRowSkeleton({ count = 4 }) {
  return (
    <div className="product-grid">
      {Array.from({ length: count }, (_, i) => (
        <ProductCardSkeleton key={i} />
      ))}
    </div>
  );
}

CardRowSkeleton.propTypes = { count: PropTypes.number };

export function HeroSkeleton() {
  return <div className="skeleton hero hero--skeleton" aria-hidden="true" />;
}
