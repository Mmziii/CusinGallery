import PropTypes from "prop-types";

/**
 * <picture>/srcset wrapper (Part 3): when the API supplies responsive
 * WebP variants (400/800/1200), serves them with sizes hints; otherwise
 * falls back to the original. The original is always the <img> src so a
 * missing variant file can never break rendering. Layout-shift-free:
 * callers reserve space via CSS aspect-ratio on the wrapper.
 */
function SmartImage({ image, alt, className, eager = false, sizes }) {
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
        src={image?.image}
        alt={alt || ""}
        className={className}
        loading={eager ? "eager" : "lazy"}
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
