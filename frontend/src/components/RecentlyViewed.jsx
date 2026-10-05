/**
 * Part R5 item 10: «اخیراً دیده‌اید» -- hydrates the browser-local
 * recently-viewed ids through the existing ?ids= filter and renders a
 * ProductCard row. Unavailable products (deleted/deactivated since the
 * view) simply never come back from the API, so they drop silently;
 * when nothing remains, the section renders nothing at all.
 */
import PropTypes from "prop-types";
import { useMemo } from "react";

import ProductCard from "./ProductCard";
import { useAsync } from "../hooks/useAsync";
import { listProducts } from "../services/catalogApi";
import { getRecentlyViewed } from "../utils/recentlyViewed";

function RecentlyViewed({ limit = 8 }) {
  // Snapshot once per mount: the widget sits below the fold and must not
  // reshuffle while the visitor browses (the PDP records views on load).
  const ids = useMemo(() => getRecentlyViewed().slice(0, limit), [limit]);

  const state = useAsync(
    () =>
      ids.length === 0
        ? Promise.resolve({ results: [] })
        : listProducts({ ids: ids.join(","), page_size: ids.length }),
    [ids.join(",")]
  );

  const ordered = useMemo(() => {
    const rows = state.data?.results || [];
    const rank = new Map(ids.map((id, i) => [id, i]));
    return [...rows].sort((a, b) => (rank.get(a.id) ?? 99) - (rank.get(b.id) ?? 99));
  }, [state.data, ids]);

  if (ids.length === 0 || ordered.length === 0) return null;

  return (
    <section className="recently-viewed">
      <h2>اخیراً دیده‌اید</h2>
      <div className="product-grid">
        {ordered.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
    </section>
  );
}

RecentlyViewed.propTypes = { limit: PropTypes.number };

export default RecentlyViewed;
