import PropTypes from "prop-types";
import { useEffect, useId, useRef, useState, useCallback } from "react";
import Portal from "./Portal";
import { normalizePersianText } from "../utils/persianText";
import { useMediaQuery } from "../hooks/useMediaQuery";

/**
 * Editable ARIA combobox:
 * - On desktop: an attached absolute dropdown that stays anchored to its field
 *   on page scroll and inside scrollable containers, flipping above when room below is tight.
 * - On phones (<768px): a viewport-level bottom sheet with backdrop, title,
 *   focused search input, and body scroll lock.
 */
export default function SearchCombobox({
  id,
  label,
  title,
  value,
  options = [],
  onChange,
  disabled = false,
  placeholder,
  invalid = false,
}) {
  const listId = useId();
  const inputRef = useRef(null);
  const mobileSearchRef = useRef(null);
  const dropdownRef = useRef(null);
  const sheetRef = useRef(null);

  const isMobile = useMediaQuery("(max-width: 767px)");

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [flipped, setFlipped] = useState(false);

  const selectedOption = options.find((opt) => opt.value === value);
  const selectedLabel = selectedOption?.label || "";

  const normQuery = normalizePersianText(query);
  const filtered = normQuery
    ? options.filter((option) => normalizePersianText(option.label).includes(normQuery))
    : options;

  const sheetTitle = title || (label.startsWith("انتخاب") ? label : `انتخاب ${label}`);

  const updateFlip = useCallback(() => {
    if (!inputRef.current) return;
    const rect = inputRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    if (spaceBelow < 290 && spaceAbove > spaceBelow) {
      setFlipped(true);
    } else {
      setFlipped(false);
    }
  }, []);

  const openCombobox = () => {
    if (disabled) return;
    setQuery("");
    setActive(0);
    updateFlip();
    setOpen(true);
  };

  const closeCombobox = () => {
    setOpen(false);
    setQuery("");
  };

  const choose = (option) => {
    if (!option) return;
    onChange(option.value);
    closeCombobox();
    inputRef.current?.focus();
  };

  // Flip check on scroll/resize when open on desktop
  useEffect(() => {
    if (!open || isMobile) return;
    updateFlip();
    window.addEventListener("scroll", updateFlip, { passive: true });
    window.addEventListener("resize", updateFlip);
    return () => {
      window.removeEventListener("scroll", updateFlip);
      window.removeEventListener("resize", updateFlip);
    };
  }, [open, isMobile, updateFlip]);

  // Outside click listener
  useEffect(() => {
    if (!open) return;
    const outside = (event) => {
      if (
        inputRef.current?.contains(event.target) ||
        dropdownRef.current?.contains(event.target) ||
        sheetRef.current?.contains(event.target)
      ) {
        return;
      }
      closeCombobox();
    };
    const onKey = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeCombobox();
        inputRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Lock body scroll when mobile sheet is open
  useEffect(() => {
    if (!open || !isMobile) return;
    const body = document.body;
    const root = document.documentElement;
    const priorCompensation = body.style.getPropertyValue("--overlay-scrollbar-compensation");
    const priorPriority = body.style.getPropertyPriority("--overlay-scrollbar-compensation");
    const viewportWidth = root.clientWidth;
    const gutter = viewportWidth > 0 ? Math.max(0, window.innerWidth - viewportWidth) : 0;

    body.style.setProperty("--overlay-scrollbar-compensation", `${gutter}px`);
    body.classList.add("body--scroll-locked");
    root.classList.add("html--scroll-locked");

    // Focus search box on mobile
    const timer = setTimeout(() => {
      mobileSearchRef.current?.focus();
    }, 50);

    return () => {
      clearTimeout(timer);
      body.classList.remove("body--scroll-locked");
      root.classList.remove("html--scroll-locked");
      if (priorCompensation) {
        body.style.setProperty("--overlay-scrollbar-compensation", priorCompensation, priorPriority);
      } else {
        body.style.removeProperty("--overlay-scrollbar-compensation");
      }
    };
  }, [open, isMobile]);

  // Scroll active option into view
  useEffect(() => {
    if (!open) return;
    const activeEl = document.getElementById(`${listId}-${active}`);
    activeEl?.scrollIntoView?.({ block: "nearest" });
  }, [active, open, listId]);

  const handleKeyDown = (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) {
        openCombobox();
      } else {
        setActive((prev) => Math.min(filtered.length - 1, prev + 1));
      }
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        openCombobox();
      } else {
        setActive((prev) => Math.max(0, prev - 1));
      }
    } else if (event.key === "Enter") {
      if (open) {
        event.preventDefault();
        if (filtered[active]) {
          choose(filtered[active]);
        }
      }
    } else if (event.key === "Escape") {
      if (open) {
        event.preventDefault();
        closeCombobox();
        inputRef.current?.focus();
      }
    } else if (event.key === "Tab") {
      if (open) {
        closeCombobox();
      }
    }
  };

  return (
    <span className="search-combobox">
      <input
        id={id}
        ref={inputRef}
        role="combobox"
        aria-label={label}
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && filtered[active] ? `${listId}-${active}` : undefined}
        aria-invalid={invalid}
        disabled={disabled}
        placeholder={placeholder}
        autoComplete="off"
        value={open && !isMobile ? query : selectedLabel}
        onClick={openCombobox}
        onKeyDown={handleKeyDown}
        onChange={(event) => {
          const text = event.target.value;
          if (!open) openCombobox();
          setQuery(text);
          setActive(0);
          const exact = options.find((opt) => normalizePersianText(opt.label) === normalizePersianText(text));
          if (exact) onChange(exact.value);
        }}
      />

      {/* Desktop attached dropdown */}
      {open && !isMobile && (
        <span
          ref={dropdownRef}
          role="listbox"
          id={listId}
          aria-label={label}
          className={`combobox-dropdown ${flipped ? "combobox-dropdown--flipped" : ""}`}
        >
          {filtered.map((option, index) => (
            <span
              role="option"
              id={`${listId}-${index}`}
              key={option.value}
              aria-selected={option.value === value}
              className={`combobox-option ${index === active ? "is-active" : ""}`}
              onMouseDown={(event) => event.preventDefault()}
              onClick={(event) => {
                event.preventDefault();
                choose(option);
              }}
            >
              {option.label}
            </span>
          ))}
          {!filtered.length && <span className="muted combobox-empty">نتیجه‌ای پیدا نشد.</span>}
        </span>
      )}

      {/* Mobile bottom sheet */}
      {open && isMobile && (
        <Portal>
          <div
            className="combobox-backdrop"
            onClick={() => {
              closeCombobox();
              inputRef.current?.focus();
            }}
          />
          <div
            ref={sheetRef}
            role="dialog"
            aria-modal="true"
            aria-label={sheetTitle}
            className="combobox-sheet"
          >
            <div className="combobox-sheet__head">
              <span className="combobox-sheet__title">{sheetTitle}</span>
              <button
                type="button"
                className="combobox-sheet__close"
                aria-label="بستن فهرست"
                onClick={() => {
                  closeCombobox();
                  inputRef.current?.focus();
                }}
              >
                ×
              </button>
            </div>
            <div className="combobox-sheet__search-box">
              <input
                ref={mobileSearchRef}
                className="combobox-sheet__search"
                aria-label={`جستجوی ${label}`}
                placeholder={`جستجوی ${label}…`}
                value={query}
                autoFocus
                onChange={(event) => {
                  setQuery(event.target.value);
                  setActive(0);
                }}
                onKeyDown={handleKeyDown}
              />
            </div>
            <div role="listbox" id={listId} aria-label={label} className="combobox-sheet__options">
              {filtered.map((option, index) => (
                <div
                  role="option"
                  id={`${listId}-${index}`}
                  key={option.value}
                  aria-selected={option.value === value}
                  className={`combobox-option ${index === active ? "is-active" : ""}`}
                  onClick={(event) => {
                    event.preventDefault();
                    choose(option);
                  }}
                >
                  {option.label}
                </div>
              ))}
              {!filtered.length && <div className="muted combobox-empty">نتیجه‌ای پیدا نشد.</div>}
            </div>
          </div>
        </Portal>
      )}
    </span>
  );
}

SearchCombobox.propTypes = {
  id: PropTypes.string,
  label: PropTypes.string.isRequired,
  title: PropTypes.string,
  value: PropTypes.string,
  options: PropTypes.arrayOf(
    PropTypes.shape({
      value: PropTypes.string,
      label: PropTypes.string,
    })
  ).isRequired,
  onChange: PropTypes.func.isRequired,
  disabled: PropTypes.bool,
  placeholder: PropTypes.string,
  invalid: PropTypes.bool,
};
