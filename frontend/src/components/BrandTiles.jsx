import { Link } from "react-router-dom";

import useReveal from "../hooks/useReveal";
import { useAsync } from "../hooks/useAsync";
import { listBrands } from "../services/catalogApi";
import SmartImage from "./SmartImage";

/**
 * Featured brand tiles (Part R2): large rounded image tiles for the
 * brands the owner marked is_featured in admin (ordered display_order),
 * in the spirit of big-tile rows on large marketplaces but with our own
 * boutique look. Each tile links to /shop/?brand=<slug>. Hidden entirely
 * when no brand is featured.
 */
function BrandTiles() {
  const ref = useReveal();
  const { data } = useAsync(() => listBrands({ is_featured: "true" }), []);
  const brands = data?.results || [];

  if (!brands.length) return null;

  return (
    <section className="section container reveal" ref={ref}>
      <div className="section__head">
        <h2>برندهای منتخب</h2>
        <span className="section__rule" aria-hidden="true" />
      </div>
      <div className="brand-tiles">
        {brands.map((brand) => (
          <Link
            key={brand.id}
            to={`/shop/?brand=${encodeURIComponent(brand.slug)}`}
            className="brand-tile"
          >
            {/* Part S4 item 1: the tile image, else the brand logo on a
                tinted field, else the shared placeholder -- all through the
                same component, so a broken file degrades identically. */}
            <span
              className={`brand-tile__media ${!brand.tile_image && brand.logo ? "brand-tile__media--tinted" : ""}`}
            >
              <SmartImage image={brand.tile_image || brand.logo || null} alt={brand.name} />
            </span>
            <span className="brand-tile__name">{brand.name}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

export default BrandTiles;
