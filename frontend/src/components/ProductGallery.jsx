import PropTypes from "prop-types";
import { useCallback, useEffect, useRef, useState } from "react";

import SmartImage from "./SmartImage";

/**
 * Product gallery (Part S5 item 3): the main image large, a row of small
 * thumbnails of the other images directly under it.
 *
 * Behaviour:
 *  - click/tap a thumbnail selects it; the main image cross-fades (~200ms)
 *    while the previous one fades out underneath, so there is no blank
 *    frame and no layout shift (the stage keeps its height);
 *  - the thumbnail row is an ARIA tablist: ArrowRight/ArrowLeft (RTL-aware)
 *    move the selection and the focus, Home/End jump to the ends, and every
 *    thumbnail is a real button so Enter/Space work as usual;
 *  - on small screens the row scrolls horizontally with scroll-snap and
 *    scrolls the active thumbnail into view; the main image supports swipe;
 *  - click-to-zoom still works (the same .product-detail__main-img class),
 *    and the zoom resets when the image changes;
 *  - a single-image product renders no thumbnail row at all;
 *  - every image (main and thumbnails) goes through SmartImage, so a
 *    missing or broken file shows the shared placeholder.
 *  - prefers-reduced-motion: no cross-fade animation (CSS handles it).
 */
function ProductGallery({ images, name }) {
  const [active, setActive] = useState(0);
  const [previous, setPrevious] = useState(null);
  const [zoomed, setZoomed] = useState(false);
  const thumbRefs = useRef([]);
  const fadeTimer = useRef(null);
  const touchX = useRef(null);
  // Set when a swipe just happened, so the click the browser fires at the
  // end of the gesture does not also toggle the zoom.
  const swiped = useRef(false);
  // The latest selection, readable outside React's state-update cycle so
  // `select` stays a pure event handler (no side effects inside an updater).
  const activeRef = useRef(active);
  activeRef.current = active;

  const count = images?.length || 0;
  const current = count ? images[Math.min(active, count - 1)] : null;
  const previousImage = previous != null && count ? images[previous] : null;

  // A new product (or a changed image list) starts from the first image.
  useEffect(() => {
    setActive(0);
    setPrevious(null);
    setZoomed(false);
  }, [name, count]);

  useEffect(() => () => clearTimeout(fadeTimer.current), []);

  const select = useCallback(
    (index) => {
      const currentIndex = activeRef.current;
      if (index < 0 || index >= count || index === currentIndex) return;
      setPrevious(currentIndex);
      setActive(index);
      setZoomed(false);
      clearTimeout(fadeTimer.current);
      // The outgoing layer is dropped once the 200ms cross-fade is done.
      fadeTimer.current = setTimeout(() => setPrevious(null), 220);
    },
    [count]
  );

  const focusThumb = (index) => {
    thumbRefs.current[index]?.focus();
  };

  // RTL: the row reads right-to-left, so ArrowRight goes to the previous
  // image and ArrowLeft to the next one.
  const onKeyDown = (event) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      const next = Math.max(0, active - 1);
      select(next);
      focusThumb(next);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      const next = Math.min(count - 1, active + 1);
      select(next);
      focusThumb(next);
    } else if (event.key === "Home") {
      event.preventDefault();
      select(0);
      focusThumb(0);
    } else if (event.key === "End") {
      event.preventDefault();
      select(count - 1);
      focusThumb(count - 1);
    }
  };

  // Keep the active thumbnail visible while the row scrolls horizontally.
  useEffect(() => {
    const node = thumbRefs.current[active];
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }, [active]);

  if (!count) {
    return (
      <div className="product-gallery">
        <div className="product-gallery__stage">
          <SmartImage image={null} alt={name} className="product-detail__main-img" />
        </div>
      </div>
    );
  }

  return (
    <div className="product-gallery">
      <div
        className="product-gallery__stage"
        role="tabpanel"
        aria-label={name}
        onClick={() => {
          if (swiped.current) {
            swiped.current = false;
            return;
          }
          setZoomed((z) => !z);
        }}
        onTouchStart={(event) => {
          touchX.current = event.touches[0].clientX;
        }}
        onTouchEnd={(event) => {
          if (touchX.current === null) return;
          const dx = event.changedTouches[0].clientX - touchX.current;
          touchX.current = null;
          if (Math.abs(dx) < 48) return;
          swiped.current = true;
          if (dx > 0) select(active - 1);
          else select(active + 1);
        }}
      >
        {previousImage && previousImage !== current ? (
          <div className="product-gallery__layer product-gallery__layer--leaving" aria-hidden="true">
            <SmartImage
              image={previousImage}
              alt=""
              className="product-detail__main-img"
              eager
            />
          </div>
        ) : null}
        <div className="product-gallery__layer product-gallery__layer--active">
          <SmartImage
            key={current?.id ?? active}
            image={current}
            alt={current?.alt_text || name}
            className={`product-detail__main-img ${zoomed ? "is-zoomed" : ""}`}
            eager
          />
        </div>
      </div>

      {count > 1 ? (
        <div
          className="product-detail__thumbs product-gallery__thumbs"
          role="tablist"
          aria-label="تصاویر محصول"
          onKeyDown={onKeyDown}
        >
          {images.map((image, index) => (
            <button
              key={image.id ?? index}
              type="button"
              role="tab"
              aria-selected={index === active}
              aria-label={`تصویر ${index + 1}`}
              tabIndex={index === active ? 0 : -1}
              ref={(node) => {
                thumbRefs.current[index] = node;
              }}
              className={index === active ? "thumb thumb--active" : "thumb"}
              onClick={() => select(index)}
            >
              <SmartImage image={image} alt="" />
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

ProductGallery.propTypes = {
  images: PropTypes.arrayOf(PropTypes.object),
  name: PropTypes.string,
};

export default ProductGallery;
