import { useEffect, useState } from "react";
import PropTypes from "prop-types";

/**
 * Consistent "no image" placeholder (Part R1): light warm-grey field with
 * the owner's brand mark (frontend/public/brand/mark.svg, used as a CSS mask
 * so the file itself is never modified) centered in brand olive green at
 * reduced opacity. The wrapper fills whatever IMAGE AREA the caller reserves
 * (same aspect ratio as real images) so the layout never shifts.
 */
export function ImagePlaceholder({ label, className = "" }) {
  return (
    <span className={`img-placeholder ${className}`} role="img" aria-label={label || "بدون تصویر"}>
      <span className="img-placeholder__mark" aria-hidden="true" />
    </span>
  );
}

ImagePlaceholder.propTypes = {
  label: PropTypes.string,
  className: PropTypes.string,
};

/**
 * <picture>/srcset wrapper (Part 3, hardened in Part R1): when the API
 * supplies responsive WebP variants (400/800/1200), serves them with sizes
 * hints; otherwise falls back to the original. The original is always the
 * <img> src so a missing variant file can never break rendering.
 *
 * Missing OR broken images (onError) render the shared ImagePlaceholder in
 * the image area only, so every surface (cards, gallery, mini-cart, cart,
 * wishlist, orders, suggestions, related) degrades identically.
 */
function SmartImage({ image, alt, className, eager = false, sizes }) {
  const src = image?.image || null;
  const [failed, setFailed] = useState(false);

  // A new src (e.g. switching gallery image) gets a fresh chance.
  useEffect(() => setFailed(false), [src]);

  if (!src || failed) {
    // Context CSS (storefront.css) sizes the placeholder exactly like the
    // <img>/<picture> it replaces, so the layout never shifts.
    return <ImagePlaceholder label={alt} />;
  }

  const hasVariants = Boolean(image?.webp_400 || image?.webp_800 || image?.webp_1200);

  return (
    <picture>
      {hasVariants ? (
        <source
          type="image/webp"
          srcSet={[
            image.webp_400 ? `${image.webp_400} 400w` : null,
            image.webp_800 ? `${image.webp_800} 800w` : null,
            image.webp_1200 ? `${image.webp_1200} 1200w` : null,
          ]
            .filter(Boolean)
            .join(", ")}
          sizes={sizes || "(max-width: 600px) 45vw, (max-width: 1000px) 30vw, 25vw"}
        />
      ) : null}
      <img
        src={src}
        alt={alt || ""}
        className={className}
        loading={eager ? "eager" : "lazy"}
        onError={() => setFailed(true)}
      />
    </picture>
  );
}

SmartImage.propTypes = {
  image: PropTypes.shape({
    image: PropTypes.string,
    webp_400: PropTypes.string,
    webp_800: PropTypes.string,
    webp_1200: PropTypes.string,
  }),
  alt: PropTypes.string,
  className: PropTypes.string,
  eager: PropTypes.bool,
  sizes: PropTypes.string,
};

export default SmartImage;
