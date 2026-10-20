import { useEffect, useRef, useState } from "react";
import PropTypes from "prop-types";
import { Link } from "react-router-dom";

import Icon from "./Icon";
import Portal from "./Portal";
import SmartImage from "./SmartImage";
import useFocusTrap from "../hooks/useFocusTrap";
import { isDesktopViewport } from "../utils/viewport";

/**
 * Stage 2: the «دسته‌بندی کالاها» mega menu (Digikala style).
 *
 * Desktop (≥1024px, decided by CSS): a panel under the header,
 * opened by HOVER with a ~150 ms intent delay (so it never
 * flickers when the pointer passes by) and by click/Enter
 * (touch laptops, keyboard); closed by mouse-leave (~200 ms
 * grace), Escape or an outside click. Right column: the main
 * categories (icon + name). Hovering one lists its
 * sub-categories on the left in columns -- each sub-category a
 * bold heading (with «›») and its children under it, plus a
 * «همهٔ محصولات <category> ›» link on top. The active main
 * category carries a gold line on the right. The panel scrolls
 * on its own (max-height 70vh), never the page, over a dimmed
 * overlay.
 *
 * Phone/tablet (<1024px): the same button opens a full-height
 * sheet sliding in from the right (250 ms) with drill-down
 * navigation: tap a main category to slide to its children,
 * «بازگشت» to go back, and «مشاهدهٔ همه» at the top of
 * every level. Body scroll is locked while it is open.
 *
 * Both surfaces are rendered whenever the menu is open and the
 * WRONG one is hidden by a CSS media query -- hover handlers
 * stay attached (touch laptops get hover AND click) while a
 * phone only ever sees the sheet.
 */
const OPEN_DELAY_MS = 150; // hover intent: don't flicker
const CLOSE_DELAY_MS = 200; // grace: cross the gap to the panel

export default function MegaMenu({ groups, open, onOpen, onClose }) {
  const [activeId, setActiveId] = useState(null);
  // Mobile drill-down: a stack of drilled-into categories.
  const [stack, setStack] = useState([]);
  // Which way the sheet's level list last moved (for the
  // slide direction).
  const [drillForward, setDrillForward] = useState(true);

  const triggerRef = useRef(null);
  const sheetRef = useRef(null);
  const openTimer = useRef(null);
  const closeTimer = useRef(null);
  const focusPending = useRef(false);

  const active =
    groups.find((category) => category.id === activeId) || groups[0] || null;

  const cancelOpen = () => {
    if (openTimer.current) {
      clearTimeout(openTimer.current);
      openTimer.current = null;
    }
  };
  const cancelClose = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };
  const requestOpen = () => {
    cancelClose();
    if (open) return;
    cancelOpen();
    openTimer.current = setTimeout(onOpen, OPEN_DELAY_MS);
  };
  const openNow = () => {
    cancelClose();
    cancelOpen();
    if (!open) {
      focusPending.current = true;
      onOpen();
    }
  };
  const scheduleClose = () => {
    cancelOpen();
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(onClose, CLOSE_DELAY_MS);
  };
  const close = () => {
    cancelOpen();
    cancelClose();
    onClose();
  };

  // Timers die with the component / on every state change.
  useEffect(
    () => () => {
      cancelOpen();
      cancelClose();
    },
    []
  );

  // Escape closes (both surfaces) and hands focus back to the
  // trigger button.
  useEffect(() => {
    if (!open) return undefined;
    function onKey(event) {
      if (event.key === "Escape") {
        event.stopPropagation();
        close();
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  // Outside click closes (desktop panel AND mobile sheet).
  // The desktop panel is within the trigger wrapper; the
  // dimming overlay is a sibling and counts as outside too.
  useEffect(() => {
    if (!open) return undefined;
    function onClick(event) {
      const path = typeof event.composedPath === "function" ? event.composedPath() : [];
      if (
        (sheetRef.current && (sheetRef.current.contains(event.target) || path.includes(sheetRef.current))) ||
        (triggerRef.current && (triggerRef.current.contains(event.target) || path.includes(triggerRef.current)))
      ) {
        return;
      }
      close();
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  // Focus trap for the mobile sheet (a real dialog --
  // only where CSS shows it; on desktop the hover
  // panel must never trap keyboard focus).
  useFocusTrap(sheetRef, open && !isDesktopViewport(), close);

  // Keyboard open (click/Enter): land focus on the first main
  // category so Tab users are inside the menu, not on the
  // trigger they just used.
  useEffect(() => {
    if (!open || !focusPending.current) return;
    focusPending.current = false;
    const first = triggerRef.current?.querySelector(
      ".mega-menu__roots button"
    );
    first?.focus();
  }, [open, activeId]);

  // Arrow keys move along a list of menu items (RTL-aware:
  // Left/Down are "forward").
  const rovingKeys = (event) => {
    const keys = [
      "ArrowDown",
      "ArrowUp",
      "ArrowLeft",
      "ArrowRight",
      "Home",
      "End",
    ];
    if (!keys.includes(event.key)) return;
    const items = [...event.currentTarget.querySelectorAll("button, a[href]")];
    const index = items.indexOf(document.activeElement);
    if (index === -1) return;
    event.preventDefault();
    const forward = event.key === "ArrowDown" || event.key === "ArrowLeft";
    let next = index;
    if (event.key === "Home") next = 0;
    else if (event.key === "End") next = items.length - 1;
    else next = (index + (forward ? 1 : -1) + items.length) % items.length;
    items[next]?.focus();
  };

  const touchStartRef = useRef(null);
  const handleTouchStart = (event) => {
    const touch = event.touches[0];
    if (touch) {
      touchStartRef.current = { x: touch.clientX, y: touch.clientY };
    }
  };
  const handleTouchEnd = (event, action) => {
    if (!touchStartRef.current) return;
    const touch = event.changedTouches[0];
    if (!touch) return;
    const dx = Math.abs(touch.clientX - touchStartRef.current.x);
    const dy = Math.abs(touch.clientY - touchStartRef.current.y);
    touchStartRef.current = null;
    // Only trigger if it is a genuine tap, not a scroll gesture
    if (dx < 12 && dy < 12) {
      event.preventDefault();
      event.stopPropagation();
      action();
    }
  };

  const drillInto = (category) => {
    setDrillForward(true);
    setStack((current) => [...current, category]);
  };
  const drillBack = () => {
    setDrillForward(false);
    setStack((current) => current.slice(0, -1));
  };
  const sheetLevel = stack[stack.length - 1] || null;
  const sheetItems = sheetLevel
    ? sheetLevel.children || []
    : groups;
  const sheetTitle = sheetLevel ? sheetLevel.name : "دسته‌بندی کالاها";

  const panelId = "mega-menu-panel";
  const sheetId = "mega-menu-sheet";

  return (
    <>
      {open ? (
        <div
          className="mega-menu__overlay"
          aria-hidden="true"
          onClick={close}
        />
      ) : null}
      <div
        className={`site-header__mega-trigger${open ? " is-open" : ""}`}
        ref={triggerRef}
        onMouseEnter={requestOpen}
        onMouseLeave={scheduleClose}
      >
        <button
          type="button"
          className="site-header__mega-btn"
          aria-haspopup="true"
          aria-expanded={open}
          aria-controls={`${panelId} ${sheetId}`}
          aria-label="دسته‌بندی کالاها"
          onClick={() => {
            if (open) {
              close();
            } else {
              openNow();
            }
          }}
        >
          <Icon name="grid" size={16} />
          {/* PR 20: the 768-1099px range shows the SHORT label (CSS swaps
              them); the accessible name stays «دسته‌بندی کالاها» either
              way via the aria-label above. */}
          <span className="site-header__mega-label">دسته‌بندی کالاها</span>
          <span className="site-header__mega-label site-header__mega-label--short" aria-hidden="true">
            دسته‌بندی
          </span>
          <Icon name="chevron-down" size={16} />
        </button>

        {/* Desktop panel (CSS hides it below 1024px).
            Mounted only while open: the fade+slide
            keyframe runs on entry (mount animation, the
            same pattern as the drawers). */}
        {open ? (
        <div
          className="mega-menu"
          id={panelId}
          onMouseEnter={cancelClose}
          onMouseLeave={scheduleClose}
        >
          <div className="mega-menu__inner" aria-label="دسته‌بندی کالاها">
            <ul className="mega-menu__roots" onKeyDown={rovingKeys}>
              {groups.map((category) => (
                <li key={category.id}>
                  <button
                    type="button"
                    className={active?.id === category.id ? "is-active" : ""}
                    onMouseEnter={() => setActiveId(category.id)}
                    onFocus={() => setActiveId(category.id)}
                    onClick={() => setActiveId(category.id)}
                  >
                    <span className="mega-menu__root-icon">
                      {category.image ? (
                        <SmartImage image={category.image} alt="" />
                      ) : (
                        <Icon name="grid" size={20} />
                      )}
                    </span>
                    <span className="mega-menu__root-name">
                      {category.name}
                    </span>
                    {(category.children || []).length > 0 ? (
                      <Icon name="chevron-left" size={14} />
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
            {active ? (
              <div className="mega-menu__panel">
                <Link
                  className="mega-menu__all"
                  to={`/shop/?category=${encodeURIComponent(active.slug)}`}
                  onClick={close}
                >
                  همهٔ محصولات {active.name}
                  <Icon name="chevron-left" size={14} />
                </Link>
                <div className="mega-menu__columns" onKeyDown={rovingKeys}>
                  {(active.children || []).map((sub) => (
                    <div className="mega-menu__col" key={sub.id}>
                      <Link
                        className="mega-menu__subhead"
                        to={`/shop/?category=${encodeURIComponent(sub.slug)}`}
                        onClick={close}
                      >
                        {sub.name}
                        <span aria-hidden="true"> ›</span>
                      </Link>
                      <ul>
                        {(sub.children || []).map((child) => (
                          <li key={child.id}>
                            <Link
                              to={`/shop/?category=${encodeURIComponent(
                                child.slug
                              )}`}
                              onClick={close}
                            >
                              {child.name}
                            </Link>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
        ) : null}
      </div>

      {/* Mobile/tablet sheet (CSS hides it at ≥1024px).
          Portaled like the other full-screen drawers; its
          scroll lock lives in Header (it owns the drawer
          state), the focus trap here. */}
      {open ? (
        <Portal>
          <div
            className="mega-sheet"
            id={sheetId}
            role="dialog"
            aria-modal="true"
            aria-label="دسته‌بندی کالاها"
          >
            <div className="mega-sheet__backdrop" onClick={close} />
            <div className="mega-sheet__panel" ref={sheetRef}>
              <div className="mega-sheet__head">
                {stack.length > 0 ? (
                  <button
                    type="button"
                    className="mega-sheet__back"
                    onClick={drillBack}
                    onTouchStart={handleTouchStart}
                    onTouchEnd={(e) => handleTouchEnd(e, drillBack)}
                  >
                    <Icon name="chevron-right" size={18} />
                    بازگشت
                  </button>
                ) : (
                  <span className="mega-sheet__head-spacer" />
                )}
                <h2 className="mega-sheet__title">{sheetTitle}</h2>
                <button
                  type="button"
                  className="mega-sheet__close"
                  aria-label="بستن دسته‌بندی‌ها"
                  onClick={close}
                >
                  <Icon name="close" size={20} />
                </button>
              </div>
              <Link
                className="mega-sheet__all"
                to={
                  sheetLevel
                    ? `/shop/?category=${encodeURIComponent(sheetLevel.slug)}`
                    : "/shop/"
                }
                onClick={close}
              >
                مشاهدهٔ همه
                {sheetLevel ? ` ${sheetLevel.name}` : ""}
                <Icon name="chevron-left" size={14} />
              </Link>
              <ul
                className="mega-sheet__list"
                key={sheetLevel ? sheetLevel.id : "root"}
                data-direction={drillForward ? "forward" : "back"}
                onKeyDown={rovingKeys}
              >
                {sheetItems.map((category) => {
                  const hasChildren = (category.children || []).length > 0;
                  const icon = category.image ? (
                    <SmartImage image={category.image} alt="" />
                  ) : (
                    <Icon name="grid" size={20} />
                  );
                  return (
                    <li key={category.id}>
                      {hasChildren ? (
                        <button
                          type="button"
                          onClick={() => drillInto(category)}
                          onTouchStart={handleTouchStart}
                          onTouchEnd={(e) =>
                            handleTouchEnd(e, () => drillInto(category))
                          }
                        >
                          <span className="mega-sheet__icon">{icon}</span>
                          <span>{category.name}</span>
                          <Icon
                            name="chevron-left"
                            size={16}
                            className="mega-sheet__chevron"
                          />
                        </button>
                      ) : (
                        <Link
                          to={`/shop/?category=${encodeURIComponent(
                            category.slug
                          )}`}
                          onClick={close}
                        >
                          <span className="mega-sheet__icon">{icon}</span>
                          <span>{category.name}</span>
                        </Link>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>
        </Portal>
      ) : null}
    </>
  );
}

MegaMenu.propTypes = {
  groups: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.number.isRequired,
      name: PropTypes.string.isRequired,
      slug: PropTypes.string.isRequired,
      image: PropTypes.object,
      product_count: PropTypes.number,
      children: PropTypes.array,
    })
  ).isRequired,
  open: PropTypes.bool.isRequired,
  onOpen: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
};
