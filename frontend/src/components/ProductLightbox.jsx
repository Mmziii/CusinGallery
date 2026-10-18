import PropTypes from "prop-types";
import { useEffect, useRef } from "react";

import useFocusTrap from "../hooks/useFocusTrap";
import { faDigits } from "../utils/faDigits";
import Icon from "./Icon";
import Portal from "./Portal";
import SmartImage from "./SmartImage";

/** Kept mounted while closed so the focus trap can restore the opener. */
function ProductLightbox({ open, images, name, active, previous, onSelect, onClose }) {
  const dialogRef = useRef(null);
  const thumbnailRefs = useRef([]);
  const touchStart = useRef(null);
  const count = images.length;
  useFocusTrap(dialogRef, open, onClose);

  useEffect(() => {
    if (!open) return undefined;
    const body = document.body;
    const root = document.documentElement;
    const overflow = body.style.overflow;
    const rootOverflow = root.style.overflow;
    const padding = body.style.paddingInlineEnd;
    const gutter = root.clientWidth > 0 ? Math.max(0, window.innerWidth - root.clientWidth) : 0;
    const currentPadding = parseFloat(window.getComputedStyle(body).paddingInlineEnd) || 0;
    body.style.overflow = "hidden";
    root.style.overflow = "hidden";
    if (gutter) body.style.paddingInlineEnd = `${currentPadding + gutter}px`;

    // Keep screen-reader and pointer focus out of the underlying application.
    const siblings = [...body.children]
      .filter((element) => element !== dialogRef.current)
      .map((element) => [element, element.hasAttribute("inert")]);
    siblings.forEach(([element]) => element.setAttribute("inert", ""));
    return () => {
      body.style.overflow = overflow;
      root.style.overflow = rootOverflow;
      body.style.paddingInlineEnd = padding;
      siblings.forEach(([element, wasInert]) => {
        if (!wasInert) element.removeAttribute("inert");
      });
    };
  }, [open]);

  useEffect(() => {
    if (!open || count < 2) return undefined;
    const onKeyDown = (event) => {
      if (event.defaultPrevented) return;
      // RTL: left advances through the right-to-left thumbnail strip.
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        onSelect((active + (event.key === "ArrowLeft" ? 1 : -1) + count) % count);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, active, count, onSelect]);

  useEffect(() => {
    if (open) thumbnailRefs.current[active]?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [open, active]);

  if (!open || !count) return null;
  const current = images[active];
  const leaving = previous != null ? images[previous] : null;

  return (
    <Portal>
      <div
        className="product-lightbox"
        role="dialog"
        aria-modal="true"
        aria-label={`تصاویر ${name}`}
        dir="rtl"
        ref={dialogRef}
        onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
      >
        <header className="product-lightbox__header">
          <button type="button" className="product-lightbox__button" aria-label="بستن تصاویر" onClick={onClose}>
            <Icon name="close" size={24} />
          </button>
          <p role="status" aria-live="polite" aria-atomic="true">{faDigits(active + 1)} از {faDigits(count)}</p>
          <span>{name}</span>
        </header>
        <div
          className="product-lightbox__stage"
          onTouchStart={(event) => {
            const touch = event.touches[0];
            touchStart.current = { x: touch.clientX, y: touch.clientY };
          }}
          onTouchCancel={() => { touchStart.current = null; }}
          onTouchEnd={(event) => {
            const start = touchStart.current;
            touchStart.current = null;
            if (!start || count < 2) return;
            const touch = event.changedTouches[0];
            const dx = touch.clientX - start.x;
            const dy = touch.clientY - start.y;
            if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy)) {
              onSelect((active + (dx < 0 ? 1 : -1) + count) % count);
            }
          }}
          onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
        >
          {leaving && leaving !== current ? (
            <div className="product-gallery__layer product-gallery__layer--leaving" aria-hidden="true">
              <SmartImage image={leaving} alt="" eager sizes="100vw" />
            </div>
          ) : null}
          <div key={active} className="product-gallery__layer product-gallery__layer--active">
            <SmartImage image={current} alt={faDigits(current.alt_text || name)} eager sizes="100vw" />
          </div>
          {count > 1 ? (
            <>
              <button type="button" className="product-lightbox__button product-lightbox__previous" aria-label="تصویر قبلی" onClick={() => onSelect((active - 1 + count) % count)}>
                <Icon name="chevron-right" size={28} />
              </button>
              <button type="button" className="product-lightbox__button product-lightbox__next" aria-label="تصویر بعدی" onClick={() => onSelect((active + 1) % count)}>
                <Icon name="chevron-left" size={28} />
              </button>
            </>
          ) : null}
        </div>
        {count > 1 ? (
          <div className="product-lightbox__thumbs" role="group" aria-label="تصاویر کوچک محصول">
            {images.map((image, index) => (
              <button
                key={image.id ?? index}
                ref={(node) => { thumbnailRefs.current[index] = node; }}
                type="button"
                className={`thumb${index === active ? " thumb--active" : ""}`}
                aria-label={`نمایش تصویر ${faDigits(index + 1)}`}
                aria-pressed={index === active}
                onClick={() => onSelect(index)}
              >
                <SmartImage image={image} alt="" sizes="72px" />
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </Portal>
  );
}

ProductLightbox.propTypes = {
  open: PropTypes.bool.isRequired,
  images: PropTypes.arrayOf(PropTypes.object).isRequired,
  name: PropTypes.string,
  active: PropTypes.number.isRequired,
  previous: PropTypes.number,
  onSelect: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};

export default ProductLightbox;
