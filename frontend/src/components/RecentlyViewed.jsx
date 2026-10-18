import PropTypes from "prop-types";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import Icon from "./Icon";
import ProductCard from "./ProductCard";
import { useAsync } from "../hooks/useAsync";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { listProducts } from "../services/catalogApi";
import { getRecentlyViewed, RECENT_LIMIT } from "../utils/recentlyViewed";

/** One shared scroll-snap row for the product, home and cart pages. */
function RecentlyViewed({ limit = RECENT_LIMIT, excludeId = null }) {
  const ids = useMemo(() => getRecentlyViewed(excludeId).slice(0, Math.min(limit, RECENT_LIMIT)), [limit, excludeId]);
  const trackRef = useRef(null);
  const trackId = useId();
  const [scrollable, setScrollable] = useState({ previous: false, next: false });
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const state = useAsync(
    () => ids.length ? listProducts({ ids: ids.join(",") }) : Promise.resolve({ results: [] }),
    [ids.join(",")]
  );
  const ordered = useMemo(() => {
    const rank = new Map(ids.map((id, index) => [id, index]));
    return (state.data?.results || [])
      .filter((product) => rank.has(product.id))
      .sort((a, b) => rank.get(a.id) - rank.get(b.id));
  }, [state.data, ids]);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return undefined;
    const measure = () => {
      const max = Math.max(0, track.scrollWidth - track.clientWidth);
      // Modern RTL scrollers start at 0 (right edge) and move negative.
      // Clamp Safari's elastic overscroll before deciding which arrows exist.
      const offset = Math.min(max, Math.max(0, -track.scrollLeft));
      setScrollable({ previous: offset > 1, next: offset < max - 1 });
    };
    measure();
    track.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", measure);
    const observer = new ResizeObserver(measure);
    observer.observe(track);
    return () => {
      track.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
      observer.disconnect();
    };
  }, [ordered.length]);

  const scroll = (direction) => {
    const track = trackRef.current;
    if (!track) return;
    track.scrollBy({ left: direction * -track.clientWidth * .9, behavior: reducedMotion ? "auto" : "smooth" });
  };

  if (!ids.length || !ordered.length) return null;

  return (
    <section className="recently-viewed">
      <div className="recently-viewed__heading">
        <h2>اخیراً دیده‌اید</h2>
        <div className="recently-viewed__arrows">
          {scrollable.previous ? (
            <button type="button" className="icon-btn" aria-label="محصولات قبلی" aria-controls={trackId} onClick={() => scroll(-1)}>
              <Icon name="chevron-right" size={20} />
            </button>
          ) : null}
          {scrollable.next ? (
            <button type="button" className="icon-btn" aria-label="محصولات بعدی" aria-controls={trackId} onClick={() => scroll(1)}>
              <Icon name="chevron-left" size={20} />
            </button>
          ) : null}
        </div>
      </div>
      <div
        className="recently-viewed__track"
        id={trackId}
        ref={trackRef}
        dir="rtl"
        role="region"
        aria-label="کالاهای اخیراً دیده‌شده"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return;
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            scroll(event.key === "ArrowLeft" ? 1 : -1);
          }
        }}
      >
        {ordered.map((product) => (
          <div className="recently-viewed__item" key={product.id}>
            <ProductCard product={product} />
          </div>
        ))}
      </div>
    </section>
  );
}

RecentlyViewed.propTypes = { limit: PropTypes.number, excludeId: PropTypes.number };

export default RecentlyViewed;
