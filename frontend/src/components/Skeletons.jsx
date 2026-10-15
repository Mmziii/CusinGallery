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

export function ContentSkeleton({ label = "در حال بارگذاری…" }) {
  return <div role="status" aria-label={label} aria-busy="true" className="content-skeleton">
    <span className="sr-only">{label}</span>
    <div className="skeleton skeleton--line" style={{width: "55%"}} />
    <div className="skeleton" style={{height: "180px", borderRadius: "12px"}} />
    <div className="skeleton skeleton--line" />
    <div className="skeleton skeleton--line" style={{width: "70%"}} />
  </div>;
}
ContentSkeleton.propTypes = { label: PropTypes.string };
