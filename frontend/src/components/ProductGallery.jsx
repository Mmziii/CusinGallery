import PropTypes from "prop-types";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import SmartImage from "./SmartImage";
import ProductLightbox from "./ProductLightbox";
import { faDigits } from "../utils/faDigits";

/** Product thumbnails select an image; the main button opens a modal, never an in-place zoom. */
function ProductGallery({ images, name = "محصول" }) {
  const galleryImages = useMemo(() => (images || []).filter((image) => image?.image), [images]);
  const [active, setActive] = useState(0);
  const [previous, setPrevious] = useState(null);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const closeLightbox = useCallback(() => setLightboxOpen(false), []);
  const thumbRefs = useRef([]);
  const fadeTimer = useRef(null);
  const touchX = useRef(null);
  // Set when a swipe just happened, so the click the browser fires at the
  // end of the gesture does not also open the popup.
  const swiped = useRef(false);
  // The latest selection, readable outside React's state-update cycle so
  // `select` stays a pure event handler (no side effects inside an updater).
  const activeRef = useRef(active);
  activeRef.current = active;

  const count = galleryImages.length;
  const current = count ? galleryImages[Math.min(active, count - 1)] : null;
  const previousImage = previous != null && count ? galleryImages[previous] : null;

  // A new product (or a changed image list) starts from the first image.
  useEffect(() => {
    setActive(0);
    setPrevious(null);
    setLightboxOpen(false);
  }, [name, galleryImages]);

  useEffect(() => () => clearTimeout(fadeTimer.current), []);

  const select = useCallback(
    (index) => {
      const currentIndex = activeRef.current;
      if (index < 0 || index >= count || index === currentIndex) return;
      setPrevious(currentIndex);
      setActive(index);
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
    if (lightboxOpen) return;
    const node = thumbRefs.current[active];
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }, [active, lightboxOpen]);

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
        onTouchStart={(event) => {
          swiped.current = false;
          touchX.current = event.touches[0].clientX;
        }}
        onTouchCancel={() => { touchX.current = null; swiped.current = false; }}
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
        <button
          type="button"
          className="product-gallery__open"
          aria-label={`نمایش تصاویر ${name}`}
          aria-haspopup="dialog"
          onClick={(event) => {
            if (swiped.current) {
              swiped.current = false;
              return;
            }
            event.currentTarget.focus();
            setLightboxOpen(true);
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
          <div key={active} className="product-gallery__layer product-gallery__layer--active">
            <SmartImage
              key={current?.id ?? active}
              image={current}
              alt={faDigits(current?.alt_text || name)}
              className="product-detail__main-img"
              eager
              sizes="(max-width: 767px) 100vw, 45vw"
            />
          </div>
        </button>
      </div>

      {count > 1 ? (
        <div
          className="product-detail__thumbs product-gallery__thumbs"
          role="tablist"
          aria-label="تصاویر محصول"
          onKeyDown={onKeyDown}
        >
          {galleryImages.map((image, index) => (
            <button
              key={image.id ?? index}
              type="button"
              role="tab"
              aria-selected={index === active}
              aria-label={`تصویر ${faDigits(index + 1)}`}
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
      <ProductLightbox
        open={lightboxOpen}
        images={galleryImages}
        name={name}
        active={Math.min(active, count - 1)}
        previous={previous}
        onSelect={select}
        onClose={closeLightbox}
      />
    </div>
  );
}

ProductGallery.propTypes = {
  images: PropTypes.arrayOf(PropTypes.object),
  name: PropTypes.string,
};

export default ProductGallery;
