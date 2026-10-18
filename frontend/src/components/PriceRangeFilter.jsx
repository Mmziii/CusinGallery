import PropTypes from "prop-types";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { formatPrice } from "../utils/formatPrice";

const APPLY_DELAY = 300;
const numericPrice = (value) => value !== "" && value != null && Number.isFinite(Number(value)) && Number(value) >= 0 ? Math.round(Number(value)) : null;

/** Two native, touch-accessible thumbs on ONE shared visual RTL track. */
function PriceRangeFilter({ bounds, resultRange, minimum, maximum, onApply, scopeKey }) {
  const descriptionId = useId();
  const hasBounds = bounds?.min != null && bounds?.max != null;
  const range = useMemo(() => {
    const requestedMax = numericPrice(maximum);
    const low = numericPrice(minimum) ?? Math.min(bounds?.min ?? requestedMax ?? 0, requestedMax ?? Infinity);
    const high = requestedMax ?? Math.max(bounds?.max ?? low, low);
    // Preserve explicit URL values outside this category's domain so a
    // share/back navigation never silently displays a different selection.
    return {
      min: Math.min(bounds?.min ?? low, low, high),
      max: Math.max(bounds?.max ?? high, low, high),
      selected: [Math.min(low, high), Math.max(low, high)],
    };
  }, [bounds?.min, bounds?.max, minimum, maximum]);
  const [selected, setSelected] = useState(range.selected);
  const selectedRef = useRef(selected);
  const dragging = useRef(false);
  const dirty = useRef(false);
  const timer = useRef(null);
  const latestApply = useRef(onApply);
  latestApply.current = onApply;

  useEffect(() => {
    clearTimeout(timer.current);
    dragging.current = false;
    dirty.current = false;
    selectedRef.current = range.selected;
    setSelected(range.selected);
    // Cancel pending work on any navigation/filter change, not just prices.
  }, [range, scopeKey]);
  useEffect(() => () => clearTimeout(timer.current), []);

  const scheduleApply = () => {
    if (!dirty.current || !hasBounds) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      if (!dirty.current) return;
      dirty.current = false;
      const [min, max] = selectedRef.current;
      latestApply.current({ min: min <= bounds.min ? null : min, max: max >= bounds.max ? null : max });
    }, APPLY_DELAY);
  };
  const update = (index, value) => {
    const next = [...selectedRef.current];
    const rounded = Math.round(value);
    next[index] = index === 0
      ? Math.max(range.min, Math.min(rounded, next[1]))
      : Math.min(range.max, Math.max(rounded, next[0]));
    dirty.current = true;
    selectedRef.current = next;
    setSelected(next);
  };
  const finishDrag = () => {
    dragging.current = false;
    scheduleApply();
  };
  const disabled = !hasBounds || range.min === range.max;
  const span = range.max - range.min || 1;
  const keyboardStep = Math.max(1, Math.round(span / 100));
  const onKeyDown = (event, index) => {
    let next = selectedRef.current[index];
    switch (event.key) {
      case "ArrowLeft": case "ArrowUp": next += keyboardStep; break;
      case "ArrowRight": case "ArrowDown": next -= keyboardStep; break;
      case "PageUp": next += keyboardStep * 10; break;
      case "PageDown": next -= keyboardStep * 10; break;
      case "Home": next = range.min; break;
      case "End": next = range.max; break;
      default: return;
    }
    event.preventDefault();
    clearTimeout(timer.current);
    update(index, next);
  };

  return (
    <div className="price-range" role="group" aria-label="محدوده قیمت">
      <output className="price-range__selected" aria-live="polite">
        {hasBounds ? `از ${formatPrice(selected[0])} تا ${formatPrice(selected[1])} تومان` : "محدوده قیمتی موجود نیست"}
      </output>
      <div className={`price-range__control${disabled ? " price-range__control--disabled" : ""}`} dir="rtl">
        <div className="price-range__rail" aria-hidden="true">
          <span style={{ insetInlineStart: `${(selected[0] - range.min) / span * 100}%`, insetInlineEnd: `${100 - (selected[1] - range.min) / span * 100}%` }} />
        </div>
        {["کمترین قیمت", "بیشترین قیمت"].map((label, index) => (
          <input
            key={label}
            type="range"
            className={`price-range__input price-range__input--${index === 0 ? "min" : "max"}`}
            min={range.min}
            max={range.max}
            step="any"
            style={{ zIndex: index === 0 && selected[0] === range.max ? 3 : 2 }}
            value={selected[index]}
            disabled={disabled}
            aria-label={label}
            aria-valuemin={index === 0 ? range.min : selected[0]}
            aria-valuemax={index === 0 ? selected[1] : range.max}
            aria-valuetext={`${formatPrice(selected[index])} تومان`}
            aria-describedby={descriptionId}
            onPointerDown={(event) => {
              dragging.current = true;
              clearTimeout(timer.current);
              event.currentTarget.setPointerCapture?.(event.pointerId);
            }}
            onPointerUp={finishDrag}
            onPointerCancel={finishDrag}
            onLostPointerCapture={finishDrag}
            onTouchStart={() => { dragging.current = true; clearTimeout(timer.current); }}
            onTouchEnd={finishDrag}
            onTouchCancel={finishDrag}
            onChange={(event) => {
              update(index, Number(event.target.value));
              // Also support assistive technology that changes a native
              // range without sending pointer or keyboard events.
              if (!dragging.current) scheduleApply();
            }}
            onKeyDown={(event) => onKeyDown(event, index)}
            onKeyUp={scheduleApply}
            onBlur={finishDrag}
          />
        ))}
      </div>
      <p id={descriptionId} className="price-range__extremes">
        {resultRange?.min != null && resultRange?.max != null
          ? `ارزان‌ترین: ${formatPrice(resultRange.min)} تومان — گران‌ترین: ${formatPrice(resultRange.max)} تومان`
          : "محصولی در این محدوده پیدا نشد."}
      </p>
    </div>
  );
}

const rangeShape = PropTypes.shape({ min: PropTypes.number, max: PropTypes.number });
PriceRangeFilter.propTypes = {
  bounds: rangeShape,
  resultRange: rangeShape,
  minimum: PropTypes.string,
  maximum: PropTypes.string,
  onApply: PropTypes.func.isRequired,
  scopeKey: PropTypes.string.isRequired,
};

export default PriceRangeFilter;
