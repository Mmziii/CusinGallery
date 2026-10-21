import { faDigits } from "../utils/faDigits";
import useWishlistStore from "../store/useWishlistStore";
import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";

import Icon from "./Icon";
import MegaMenu from "./MegaMenu";
import Portal from "./Portal";
import PriceTag from "./PriceTag";
import SmartImage from "./SmartImage";
import useFocusTrap from "../hooks/useFocusTrap";
import useSiteContent from "../hooks/useSiteContent";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import { getCategoryTree, listProducts } from "../services/catalogApi";
import { catalogGroups } from "../utils/categories";
import { measureBorderBoxHeight } from "../utils/headerMeasure";
import { isDesktopViewport, isPhoneViewport } from "../utils/viewport";
import {
  lineTotalForLine,
  priceInfoForLine,
  sumLineTotals,
  unitPriceForLine,
  variantLabel,
} from "../utils/cartPricing";
import { formatPrice } from "../utils/formatPrice";

/**
 * Site header (PR 19 redesign, PR 20 follow-ups): the OUTER header keeps a
 * constant height in the layout on every viewport and only the inner layer
 * changes shape.
 *
 *  - Desktop/tablet (>= 768px): the header is a fixed-height sticky box
 *    whose bar (`.site-header__inner`) morphs into a floating "pill" once
 *    scrolled. Geometry alone animates; the document height never changes.
 *  - Phone (<= 767px): the header is FIXED and a sibling spacer (rendered
 *    below) reserves the expanded header's border-box height. The expanded
 *    phone header is exactly TWO rows (burger/brand/account/cart, then a
 *    full-width search) and the inner stays `height: auto` -- never a
 *    pinned pixel value, which is what measured 190px while the search
 *    row needed 246px and spilled over the page. The fold animates with a
 *    FLIP pin (read height, pin inline, animate, clear back to auto), and
 *    because the spacer owns the flow height, collapsing can never move
 *    the document (the PR 19 scroll-anchoring loop fix).
 *
 * Scroll state uses hysteresis (compact on past 40px, off only below 8px)
 * and a short post-toggle lock that ignores scroll deltas, so a self-caused
 * scroll correction can never undo the state that caused it. The phone
 * one-row fold (`rowCollapsed`) is gated to phone viewports.
 */
function Header() {
  const wishlist = useWishlistStore();
  const { refetch: refreshWishlist, reset: resetWishlist } = wishlist;
  const location = useLocation();
  const currentRoute = `${location.pathname}${location.search}${location.hash}`;
  const previousRoute = useRef(currentRoute);
  const navigate = useNavigate();
  const { user, isAuthenticated, isLoading, logout, fetchMe } = useAuthStore();
  useEffect(() => { if (isAuthenticated) refreshWishlist(); else resetWishlist(); }, [isAuthenticated, refreshWishlist, resetWishlist]);
  const cart = useCartStore((s) => s.cart);
  const guestLines = useCartStore((s) => s.guestLines);
  const guestProducts = useCartStore((s) => s.guestProducts);
  const guestVariants = useCartStore((s) => s.guestVariants);
  const fetchCart = useCartStore((s) => s.fetchCart);
  const hydrateGuestProducts = useCartStore((s) => s.hydrateGuestProducts);

  const [searchTerm, setSearchTerm] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [menuMounted, setMenuMounted] = useState(false);
  const [menuClosing, setMenuClosing] = useState(false);
  const menuOpen = menuMounted && !menuClosing;
  const [cartOpen, setCartOpen] = useState(false);
  const [megaOpen, setMegaOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  // Desktop pill / phone shrink state. Hysteresis: it turns on past 40px and
  // only turns off below 8px, so no single-pixel boundary can flutter it.
  const [compact, setCompact] = useState(false);
  // Phone only (gated in the scroll pass): the two-row header (~120px:
  // brand/account/cart, then the full-width search) folds into one pill
  // row once the shopper has scrolled past 80px and is still going down.
  // Scrolling up by 24px -- or reaching the top -- restores it.
  const [rowCollapsed, setRowCollapsed] = useState(false);
  // The collapsed row's search icon grows the search field back into view.
  const [searchRevealed, setSearchRevealed] = useState(false);
  const [categories, setCategories] = useState([]);
  // Owner-editable brand (Task 3): name + logo come from the admin page,
  // falling back to the bundled mark until the API answers.
  const { brand } = useSiteContent();
  const brandName = brand?.name || "کازین گالری";
  const brandLogo = brand?.logo_light || brand?.logo_dark || "/brand/logo-gold.svg";
  const brandHomeLabel = `${brandName} — صفحه اصلی`;
  // The mega menu's mobile sheet is a full-viewport
  // dialog (<1024px, per CSS) -- it joins the drawers
  // that lock the document while open. (Lazy viewport
  // check, not the reactive hook: the mega menu's
  // hover handlers must work on touch laptops, and
  // re-rendering the whole header on a breakpoint
  // change buys nothing here.)
  const hasOpenDrawer =
    menuMounted || cartOpen || (megaOpen && !isDesktopViewport());
  const headerRef = useRef(null);
  const innerRef = useRef(null);
  const userMenuRef = useRef(null);
  const searchRef = useRef(null);
  const searchInputRef = useRef(null);
  // Mirrors of the two phone-header states, read by the measure effect
  // below. That effect must never re-register (nor read a stale render)
  // just because the header folded: a stale read would publish the
  // COLLAPSED height as the natural one, and the header could then never
  // animate back open.
  const rowCollapsedRef = useRef(false);
  const searchRevealedRef = useRef(false);
  // The shrink every viewport gets past 24px, mirrored for the same reason:
  // the compact header is shorter than the expanded one, so its height is
  // never a valid "natural" height either.
  const compactRef = useRef(false);
  // True while the inner's height transition is running. A mid-flight
  // offsetHeight is between the folded and expanded heights, i.e. neither.
  const animatingRef = useRef(false);
  // The transition pass's settle() (it removes the FLIP pin). The fold's
  // fallback timer reads it through this ref so a pin whose transition
  // never starts -- or never ends -- is still always released.
  const settleRef = useRef(null);
  // The fold's own fallback timer (see flipRow): armed on EVERY pin.
  const pinTimerRef = useRef(null);
  // The revealed pill search's icon. Escape on an empty field returns the
  // focus here, so the shopper's next Tab starts where they left off.
  const searchToggleRef = useRef(null);
  // The EXPANDED phone header's last measured border-box height (px). The
  // measure pass keeps it fresh; the fold's FLIP reads it as the expand
  // target before clearing back to `height: auto` at rest.
  const naturalHeightRef = useRef(0);
  // The measure pass's scheduler, so auth/cart changes (which swap the
  // account control / badge and can re-wrap the bar) can ask for a fresh
  // measurement without re-registering the whole effect.
  const scheduleMeasureRef = useRef(null);
  const searchTimer = useRef(null);
  // A response can arrive after the shopper has used the home brand action.
  // Versioning prevents that stale response from reopening suggestions.
  const searchRequestVersion = useRef(0);
  const drawerCloseTimer = useRef(null);
  const drawerRef = useRef(null);
  const minicartRef = useRef(null);
  // Stage 2: the main groups are the children of the
  // «آشپزخانه» root, pruned of categories with no
  // active products anywhere in their subtree.
  const groups = catalogGroups(categories);

  const openMenu = useCallback(() => {
    if (drawerCloseTimer.current !== null) {
      window.clearTimeout(drawerCloseTimer.current);
      drawerCloseTimer.current = null;
    }
    setMenuClosing(false);
    setMenuMounted(true);
  }, []);

  const closeMenu = useCallback((afterClose) => {
    if (!menuMounted) {
      afterClose?.();
      return;
    }
    if (menuClosing) return;

    setMenuClosing(true);
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    drawerCloseTimer.current = window.setTimeout(() => {
      setMenuMounted(false);
      setMenuClosing(false);
      drawerCloseTimer.current = null;
      afterClose?.();
    }, reducedMotion ? 0 : 250);
  }, [menuClosing, menuMounted]);

  useEffect(() => () => {
    if (drawerCloseTimer.current !== null) window.clearTimeout(drawerCloseTimer.current);
  }, []);

  useEffect(() => {
    if (previousRoute.current === currentRoute) return;
    previousRoute.current = currentRoute;
    closeMenu();
  }, [currentRoute, closeMenu]);

  // Part S2 item 8: focus trap + Escape + focus restore for the two
  // full drawers (mobile menu, mini-cart). Keep the trap and scroll lock
  // active through the menu's reverse animation, then restore focus.
  useFocusTrap(drawerRef, menuMounted, closeMenu);
  useFocusTrap(minicartRef, cartOpen, () => setCartOpen(false));

  // Both drawers are full-viewport dialogs. Lock the document while either
  // is open and reserve the exact scrollbar gutter before hiding it, so the
  // header/content do not jump horizontally when the scrollbar disappears.
  useEffect(() => {
    if (!hasOpenDrawer) return undefined;
    const body = document.body;
    const root = document.documentElement;
    const priorCompensation = body.style.getPropertyValue("--overlay-scrollbar-compensation");
    const priorPriority = body.style.getPropertyPriority("--overlay-scrollbar-compensation");
    // jsdom has no layout viewport (clientWidth is 0), while browsers do.
    // Treat that non-browser value as no scrollbar rather than reserving a
    // fake full-window width in tests or nonvisual environments.
    const viewportWidth = root.clientWidth;
    const gutter = viewportWidth > 0 ? Math.max(0, window.innerWidth - viewportWidth) : 0;

    body.style.setProperty("--overlay-scrollbar-compensation", `${gutter}px`);
    body.classList.add("body--scroll-locked");
    root.classList.add("html--scroll-locked");

    return () => {
      body.classList.remove("body--scroll-locked");
      root.classList.remove("html--scroll-locked");
      if (priorCompensation) {
        body.style.setProperty("--overlay-scrollbar-compensation", priorCompensation, priorPriority);
      } else {
        body.style.removeProperty("--overlay-scrollbar-compensation");
      }
    };
  }, [hasOpenDrawer]);

  useEffect(() => {
    fetchMe().then(({ success }) => {
      if (success) fetchCart();
    });
    getCategoryTree()
      .then(setCategories)
      .catch(() => {});
  }, [fetchMe, fetchCart]);

  useEffect(() => {
    if (!isAuthenticated && guestLines.length > 0) hydrateGuestProducts();
  }, [isAuthenticated, guestLines, hydrateGuestProducts]);

  // The collapsed row's search icon reveals the field; focus follows so the
  // phone keyboard is already up. (React commits the class change before
  // running effects, so the field is displayed by the time this fires.)
  useEffect(() => {
    if (searchRevealed) searchInputRef.current?.focus();
  }, [searchRevealed]);

  const toggleSearchReveal = () => {
    const next = !searchRevealedRef.current;
    searchRevealedRef.current = next;
    setSearchRevealed(next);
  };

  // Escape, two stages (live finding): with text in the field it clears it;
  // with an EMPTY field it closes the search row the collapsed pill grew and
  // hands the focus back to the search icon. Previously the empty case did
  // nothing, so the pill stayed in its two-row `--searching` state.
  const handleSearchKeyDown = (event) => {
    if (event.key !== "Escape") return;
    if (searchTerm) {
      event.preventDefault();
      // Bump the version so an in-flight suggestion response is discarded.
      searchRequestVersion.current += 1;
      setSearchTerm("");
      setSuggestions([]);
      return;
    }
    if (!searchRevealedRef.current) return;
    event.preventDefault();
    searchRevealedRef.current = false;
    setSearchRevealed(false);
    setSuggestions([]);
    searchToggleRef.current?.focus();
  };

  // Audit 19 / PR 20: publish the header's REAL height as
  // --site-header-height (sticky siblings and anchor scroll-margins sit
  // directly under it). What "real" means depends on the form factor:
  //
  //  - Desktop/tablet: the sticky OUTER box -- constant at
  //    var(--header-height), never the morphing pill inside it.
  //  - Phone: the EXPANDED header's border-box height. The fixed folded
  //    pill must never move the page's offsets, so on phones the same
  //    value is also published as --header-natural-height, the permanent
  //    height of `.site-header-spacer` (the fixed header's share of the
  //    document flow). variables.css seeds --site-header-height with the
  //    desktop token so it is never EMPTY before this pass runs (live:
  //    /checkout at 375px fell back to 92px anchor margins).
  //
  // The expanded phone inner is `height: auto`, so its border-box rect
  // always describes the real two rows -- no pinned pixel height can
  // re-measure itself (the 190px lock whose search row spilled over the
  // page) and no `scrollHeight` read can drop the padding (232 for 246).
  // The natural height is still measured ONLY while the header is fully
  // expanded (!rowCollapsed), not shrinking (!compact) and not animating
  // -- a folded/mid-flight frame would pin the spacer short. Re-measure
  // triggers: ResizeObserver on the expanded inner, width changes,
  // orientation, webfont load, the fold settling, and auth/cart changes
  // (the account control and badge swap size).
  useEffect(() => {
    const root = document.documentElement;
    let frame = null;
    // The refs are updated by the rAF-throttled scroll pass, which may run
    // one frame after this one; the live offset closes that gap, so a
    // measurement can never be taken while the header is compact or folded.
    const naturalCanBeMeasured = () =>
      (window.scrollY || 0) <= 40 &&
      !rowCollapsedRef.current &&
      !compactRef.current &&
      !animatingRef.current;

    const measure = () => {
      frame = null;
      const header = headerRef.current;
      const inner = innerRef.current;
      if (!header || !inner) return;
      if (!isPhoneViewport()) {
        const outer = measureBorderBoxHeight(header);
        // jsdom and hidden tabs report 0 -- keep the last real value
        // instead of pinning every sticky offset to 0.
        if (outer > 0) root.style.setProperty("--site-header-height", `${outer}px`);
        return;
      }
      if (!naturalCanBeMeasured()) return;
      const natural = measureBorderBoxHeight(inner);
      if (natural > 0) {
        naturalHeightRef.current = natural;
        root.style.setProperty("--header-natural-height", `${natural}px`);
        root.style.setProperty("--site-header-height", `${natural}px`);
      }
    };
    const schedule = () => {
      if (frame !== null) return;
      frame = window.requestAnimationFrame ? window.requestAnimationFrame(measure) : measure();
    };
    // A WIDTH change invalidates the measurement (rows wrap differently):
    // drop back to `auto` -- always safe, never clips -- and re-measure on
    // the next frame. Height-only resizes are NOT invalidating: on phones
    // the address bar collapses/expands while scrolling and fires `resize`
    // with the same width, which must not resize (or clear) the spacer.
    let lastWidth = window.innerWidth || 0;
    const onResize = () => {
      const width = window.innerWidth || 0;
      if (width === lastWidth) {
        schedule();
        return;
      }
      lastWidth = width;
      if (!rowCollapsedRef.current) root.style.removeProperty("--header-natural-height");
      schedule();
    };
    const onOrientationChange = () => {
      if (!rowCollapsedRef.current) root.style.removeProperty("--header-natural-height");
      schedule();
    };
    schedule();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", onOrientationChange);
    const resizeObserver =
      typeof ResizeObserver === "function" ? new ResizeObserver(schedule) : null;
    if (resizeObserver && innerRef.current) resizeObserver.observe(innerRef.current);
    // Webfonts change the Persian line boxes; re-measure once they are in.
    const fonts = typeof document !== "undefined" ? document.fonts : null;
    if (fonts?.ready?.then) fonts.ready.then(schedule).catch(() => {});
    // Auth/cart changes and the fold's settle point ask for a re-measure
    // through this ref (see the effects below) without re-registering
    // any of these listeners.
    scheduleMeasureRef.current = schedule;
    return () => {
      scheduleMeasureRef.current = null;
      if (frame !== null && window.cancelAnimationFrame) window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("orientationchange", onOrientationChange);
      resizeObserver?.disconnect();
    };
  }, []);

  // Sticky shrink + the phone one-row collapse.
  //
  // `compact` drives the desktop pill (and the smaller logo everywhere).
  // It is HYSTERETIC: on once y > 40, off only once y < 8. A single
  // threshold would flip on every frame that scroll anchoring nudges the
  // page a pixel or two around the boundary.
  //
  // `rowCollapsed` is the phone one-row fold. It still needs the scroll
  // DIRECTION, an offset and travel: past 80px, with 24px of cumulative
  // downward travel, the row folds; 24px of upward travel -- or reaching
  // the top (<= 10px) -- restores it.
  //
  // THE FIX for the 375x812 feedback loop (108 toggles in ~4s): collapsing
  // used to shrink the header's in-flow height by ~175px, the browser's
  // scroll anchoring corrected scrollY, and this handler read that
  // correction as an upward gesture, expanded, and looped. Two independent
  // guards now make that impossible:
  //   1. the document height is owned by a constant-height outer box (the
  //      header on desktop, the spacer on phone -- see the component), so
  //      a look change cannot move scrollY at all;
  //   2. every self-caused toggle of `compact` or `rowCollapsed` starts a
  //      350ms window in which scroll deltas are ignored. When it expires
  //      lastY is re-based to the live scrollY and both travel counters are
  //      reset, so a correction can never be banked as travel.
  // The listener is rAF-throttled: at most one state pass per frame.
  useEffect(() => {
    const TOP_ZONE = 10;
    const COMPACT_ON = 40;
    const COMPACT_OFF = 8;
    const COLLAPSE_AT = 80;
    const COLLAPSE_TRAVEL = 24;
    const EXPAND_TRAVEL = 24;
    const LOCK_MS = 350;
    let lastY = window.scrollY || 0;
    let downTravel = 0;
    let upTravel = 0;
    let frame = null;
    let lockUntil = 0;
    let unlockTimer = null;

    const schedule = () => {
      if (frame !== null) return;
      frame = window.requestAnimationFrame
        ? window.requestAnimationFrame(evaluate)
        : window.setTimeout(evaluate, 16);
    };

    const lockDeltas = () => {
      lockUntil = Date.now() + LOCK_MS;
      if (unlockTimer !== null) window.clearTimeout(unlockTimer);
      unlockTimer = window.setTimeout(() => {
        unlockTimer = null;
        lockUntil = 0;
        lastY = window.scrollY || 0;
        downTravel = 0;
        upTravel = 0;
        // The position may have changed while deltas were ignored: re-read
        // it now so the header is correct even if no further scroll fires.
        schedule();
      }, LOCK_MS);
    };

    // The collapsed class's own row height (border-box: `height` and
    // `min-height` are both the token, so the value IS the box height).
    // Returns 0 when the token cannot be resolved (e.g. jsdom), which just
    // skips the equality shortcut in flipRow.
    const rowHeightOf = (element) => {
      const raw = window.getComputedStyle?.(element)?.getPropertyValue("--header-height-row");
      const value = Number.parseFloat(raw);
      return Number.isFinite(value) && value > 0 ? value : 0;
    };

    // PR 20 FLIP for the fold. The expanded inner is `height: auto` --
    // never a pinned pixel value that can end up smaller than its
    // content -- and `auto` cannot transition. So: read the CURRENT
    // border-box height, pin it inline, force a reflow, commit the class
    // change synchronously (flushSync) while the pin holds the box, then
    // aim the box at the other end. Folding just releases the pin (the
    // collapsed class owns the row height); expanding targets the last
    // measured natural height. The transition-tracking effect below
    // clears the pin on transitionend (watchdog-covered), so at rest the
    // expanded inner is `auto` again and can never clip its rows. In
    // non-layout environments (jsdom: 0 height) the flip is skipped and
    // only the class changes. PR 21 adds two guarantees: equal heights pin
    // nothing, and every pin taken is also released by a fallback timer.
    const flipRow = (collapsing, applyState) => {
      const inner = innerRef.current;
      const from = inner ? measureBorderBoxHeight(inner) : 0;
      if (!inner || from <= 0) {
        applyState();
        return;
      }
      // (a) Nothing to animate: the box is ALREADY at the target height.
      // Live repro (375px): folded pill + search icon revealed = 128px; one
      // notch up expands the header, which is ALSO 128px. Pinning 128px over
      // 128px runs no transition, so `transitionstart` never fires and
      // `transitionend` never comes: the inline `height`/`overflow` stuck
      // forever and CLIPPED the suggestions the shopper was typing for.
      // With equal heights there is no animation to protect, so just apply
      // the state and leave the box at `height: auto`.
      const target = collapsing ? rowHeightOf(inner) : naturalHeightRef.current;
      if (target > 0 && Math.abs(target - from) <= 1) {
        applyState();
        return;
      }
      inner.style.height = `${from}px`;
      inner.style.overflow = "hidden";
      void inner.offsetHeight; // commit the pin as the transition's start
      flushSync(applyState);
      if (collapsing) {
        inner.style.removeProperty("height");
      } else if (naturalHeightRef.current > 0) {
        inner.style.height = `${naturalHeightRef.current}px`;
      } else {
        inner.style.removeProperty("height");
      }
      // (b) ALWAYS arm a fallback release. transitionstart/transitionend
      // are not guaranteed (a cancelled transition fires neither, a hidden
      // tab fires neither, and a pin that changes nothing animates at all),
      // so the pin is also released on a timer that outlives the 300ms
      // height transition. settle() is idempotent.
      if (pinTimerRef.current !== null) window.clearTimeout(pinTimerRef.current);
      pinTimerRef.current = window.setTimeout(() => {
        pinTimerRef.current = null;
        settleRef.current?.();
      }, 450);
    };

    const collapseRow = () => {
      rowCollapsedRef.current = true;
      // Folding with the search row open would keep the inner tall.
      searchRevealedRef.current = false;
      flipRow(true, () => {
        setSearchRevealed(false);
        setRowCollapsed(true);
      });
    };
    const expandRow = () => {
      rowCollapsedRef.current = false;
      flipRow(false, () => setRowCollapsed(false));
    };

    function evaluate() {
      frame = null;
      const y = window.scrollY || 0;
      const delta = y - lastY;
      lastY = y;
      let toggled = false;

      // Absolute-position hysteresis: immune to the delta lock below, so
      // the state is always truthful for where the page actually is.
      const nextCompact = compactRef.current ? y >= COMPACT_OFF : y > COMPACT_ON;
      if (nextCompact !== compactRef.current) {
        compactRef.current = nextCompact;
        setCompact(nextCompact);
        toggled = true;
      }

      const deltasLocked = Date.now() < lockUntil;
      // PR 20: the fold is a PHONE behaviour only. The class used to be
      // set on desktop too (harmless -- its styles live in the phone
      // block -- but it made the state lie about what was on screen).
      const phone = isPhoneViewport();
      if (!phone && rowCollapsedRef.current) {
        // The viewport crossed to tablet/desktop while folded (rotate,
        // resize): the wider bar must never inherit the fold.
        expandRow();
        toggled = true;
      }

      if (y <= TOP_ZONE) {
        downTravel = 0;
        upTravel = 0;
        if (rowCollapsedRef.current) {
          expandRow();
          toggled = true;
        }
        if (searchRevealedRef.current) {
          searchRevealedRef.current = false;
          setSearchRevealed(false);
        }
      } else if (!deltasLocked && phone) {
        if (delta > 0) {
          downTravel += delta;
          upTravel = 0;
          // A downward jitter must not re-fold a header the shopper just
          // opened with an upward swipe.
          if (!rowCollapsedRef.current && y > COLLAPSE_AT && downTravel >= COLLAPSE_TRAVEL) {
            collapseRow();
            toggled = true;
          }
        } else if (delta < 0) {
          upTravel += -delta;
          downTravel = 0;
          if (rowCollapsedRef.current && upTravel >= EXPAND_TRAVEL) {
            expandRow();
            toggled = true;
          }
        }
      }

      if (toggled) lockDeltas();
    }

    const onScroll = () => {
      if (frame !== null) return;
      frame = window.requestAnimationFrame
        ? window.requestAnimationFrame(evaluate)
        : window.setTimeout(evaluate, 16);
    };
    evaluate();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (unlockTimer !== null) window.clearTimeout(unlockTimer);
      if (pinTimerRef.current !== null) {
        window.clearTimeout(pinTimerRef.current);
        pinTimerRef.current = null;
      }
      if (frame === null) return;
      if (window.cancelAnimationFrame) window.cancelAnimationFrame(frame);
      else window.clearTimeout(frame);
    };
  }, []);

  // Track the inner's height transition so the measurement pass above can
  // skip the interpolated frames and then re-measure at rest -- and so the
  // fold's FLIP pin (inline height/overflow) is always released once the
  // box settles: expanded rest is `height: auto` again, folded rest is
  // the collapsed class's row height. A cancelled/interrupted transition
  // may never fire `transitionend`; the watchdog settles it instead, so
  // neither the pin nor the measurement gate can stay stuck.
  useEffect(() => {
    const inner = innerRef.current;
    if (!inner) return undefined;
    let watchdog = null;
    const settle = () => {
      animatingRef.current = false;
      inner.style.removeProperty("height");
      inner.style.removeProperty("overflow");
      if (watchdog !== null) {
        window.clearTimeout(watchdog);
        watchdog = null;
      }
      scheduleMeasureRef.current?.();
    };
    // The fold's fallback timer (Header's scroll pass) releases the pin
    // through this ref, independently of the transition events below.
    settleRef.current = settle;
    const onTransitionStart = (event) => {
      if (event.propertyName !== "height") return;
      animatingRef.current = true;
      if (watchdog !== null) window.clearTimeout(watchdog);
      watchdog = window.setTimeout(() => {
        watchdog = null;
        settle();
      }, 400);
    };
    const onTransitionEnd = (event) => {
      if (event.propertyName && event.propertyName !== "height") return;
      settle();
    };
    inner.addEventListener("transitionstart", onTransitionStart);
    inner.addEventListener("transitionend", onTransitionEnd);
    inner.addEventListener("transitioncancel", onTransitionEnd);
    return () => {
      settleRef.current = null;
      if (watchdog !== null) window.clearTimeout(watchdog);
      inner.removeEventListener("transitionstart", onTransitionStart);
      inner.removeEventListener("transitionend", onTransitionEnd);
      inner.removeEventListener("transitioncancel", onTransitionEnd);
    };
  }, []);

  // Outside click closes menus.
  useEffect(() => {
    function onClick(event) {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setUserMenuOpen(false);
      }
      if (searchRef.current && !searchRef.current.contains(event.target)) {
        setSuggestions([]);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // Debounced live suggestions.
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    const requestVersion = ++searchRequestVersion.current;
    const query = searchTerm.trim();
    if (query.length < 2) {
      setSuggestions([]);
      return undefined;
    }
    searchTimer.current = setTimeout(() => {
      listProducts({ search: query, page_size: 5 })
        .then((data) => {
          if (searchRequestVersion.current === requestVersion) setSuggestions(data.results || []);
        })
        .catch(() => {
          if (searchRequestVersion.current === requestVersion) setSuggestions([]);
        });
    }, 250);
    return () => clearTimeout(searchTimer.current);
  }, [searchTerm]);

  // The brand is the universal way home. Close every header-owned surface
  // before navigating so a portal or popup can never remain over the home
  // page. This is deliberately shared by the main header and the copies
  // inside full-screen drawers, where the original header is covered.
  const closeHeaderSurfaces = () => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchRequestVersion.current += 1;
    closeMenu();
    setCartOpen(false);
    setMegaOpen(false);
    setUserMenuOpen(false);
    setSuggestions([]);
    setSearchTerm("");
    searchRevealedRef.current = false;
    setSearchRevealed(false);
  };

  const handleHomeNavigation = () => {
    closeHeaderSurfaces();
    // A Link to the same pathname does not trigger MainLayout's pathname
    // effect. Restore the expected "go to the top" action ourselves, while
    // honouring a shopper's reduced-motion preference.
    if (location.pathname === "/" && window.scrollY > 0) {
      const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
      window.scrollTo({ top: 0, left: 0, behavior: reducedMotion ? "auto" : "smooth" });
    }
  };

  const submitSearch = (event) => {
    event.preventDefault();
    const query = searchTerm.trim();
    setSuggestions([]);
    closeMenu();
    navigate(query ? `/shop/?search=${encodeURIComponent(query)}` : "/shop/");
  };

  const handleLogout = async () => {
    setUserMenuOpen(false);
    closeMenu();
    await logout();
    navigate("/");
  };

  const itemCount = cart?.item_count ?? 0;
  // Part S5 follow-up 4 item 3: the same pricing rule as the cart page
  // (utils/cartPricing) -- `product.price` does not exist in the API, so
  // guest lines used to render an empty price and a 0 line total here too.
  const cartLines = isAuthenticated
    ? (cart?.items || []).map((item) => ({
        key: item.id,
        name: item.product?.name || "",
        image: item.product?.primary_image?.image || null,
        variant: variantLabel(item.variant),
        quantity: item.quantity,
        priceInfo: item.price_info || null,
        lineTotal: item.line_total,
      }))
    : guestLines.map((line) => {
        const product = guestProducts[line.product_id];
        const variant = line.variant_id ? guestVariants[line.variant_id] : null;
        return {
          key: `${line.product_id}-${line.variant_id ?? 0}`,
          name: product?.name || "…",
          image: product?.primary_image?.image || variant?.image?.image || null,
          variant: variantLabel(variant),
          quantity: line.quantity,
          unitPrice: unitPriceForLine(line, product, variant),
          priceInfo: priceInfoForLine(line, product, variant),
          lineTotal: lineTotalForLine(line, product, variant),
        };
      });
  const cartSubtotal = isAuthenticated
    ? (cart?.subtotal ?? null)
    : sumLineTotals(cartLines.map((line) => line.lineTotal));

  // The account control swaps between «ورود | ثبت‌نام» and the user menu,
  // the cart badge pops in/out and the owner-edited brand name can arrive
  // late -- any of those can change the expanded bar's height (a wrap on
  // a narrow phone), so ask the measure pass for a fresh read. The
  // ResizeObserver usually beats this to it; this covers swaps that keep
  // the same box height in the same frame the gate would otherwise skip.
  useEffect(() => {
    scheduleMeasureRef.current?.();
  }, [isAuthenticated, isLoading, itemCount, brandName]);

  const headerClass = [
    "site-header",
    compact && "site-header--compact",
    rowCollapsed && "site-header--collapsed",
    rowCollapsed && searchRevealed && "site-header--searching",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <>
    <header className={headerClass} ref={headerRef}>
      <div className="container site-header__inner" ref={innerRef}>
        <button
          type="button"
          className="site-header__burger"
          aria-label="بازکردن منو"
          aria-expanded={menuOpen}
          aria-controls="mobile-navigation"
          onClick={() => (menuOpen ? closeMenu() : openMenu())}
        >
          <span />
          <span />
          <span />
        </button>

        <Link
          to="/"
          className="site-header__brand"
          aria-label={brandHomeLabel}
          onClick={handleHomeNavigation}
        >
          {/* @catalog-img-allowed: the owner-uploaded brand MARK is site
              chrome, not a product/category image; it intentionally
              renders as a raw <img> (SVG-first, no catalog placeholder). */}
          <img src={brandLogo} alt="" className="site-header__logo" />
          <span className="site-header__brand-name">{brandName}</span>
        </Link>

        <div className="site-header__search" id="site-header-search" ref={searchRef} role="search">
          <form onSubmit={submitSearch}>
            <input
              type="search"
              ref={searchInputRef}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              placeholder="جستجوی محصول…"
              aria-label="جستجوی محصول"
            />
            <button type="submit" className="btn btn--gold" aria-label="جستجو">
              <Icon name="search" size={18} />
            </button>
          </form>
          {suggestions.length > 0 ? (
            <ul className="search-suggest">
              {suggestions.map((product) => (
                <li key={product.id}>
                  <Link
                    to={`/products/${product.slug}/`}
                    onClick={() => {
                      setSuggestions([]);
                      setSearchTerm("");
                    }}
                  >
                    <SmartImage image={product.primary_image} alt="" />
                    <span className="search-suggest__name">{faDigits(product.name)}</span>
                    <span className="search-suggest__price">
                      {product.price_info ? (
                        <PriceTag priceInfo={product.price_info} size="sm" />
                      ) : null}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        {/* Stage 2: the trigger lives OUTSIDE .site-header__nav so
            «دسته‌بندی کالاها» survives the tablet range hiding the text
            nav. PR 20: phones hide this trigger entirely (CSS) -- the
            two-row phone header has no room for it, and the burger drawer
            opens the same category sheet. The sheet itself renders from
            MegaMenu regardless of the trigger's visibility. */}
        <MegaMenu groups={groups} open={megaOpen} onOpen={() => setMegaOpen(true)} onClose={() => setMegaOpen(false)} />
        <nav className="site-header__nav" aria-label="ناوبری اصلی">
          <NavLink to="/shop/">فروشگاه</NavLink>
          {isAuthenticated ? <NavLink to="/wishlist/">علاقه‌مندی‌ها {wishlist.items.length > 0 ? <span key={wishlist.revision} className="wishlist-badge">{formatPrice(wishlist.items.length)}</span> : null}</NavLink> : null}
        </nav>

        <div className="site-header__actions">
          {/* The collapsed phone row's search icon. It is the only way to
              reach the field while the header is folded to one row, so it
              grows the search row back into view (see the phone block in
              storefront.css). Hidden at every other size and state. */}
          <button
            type="button"
            className="site-header__search-toggle"
            ref={searchToggleRef}
            aria-label="نمایش جستجو"
            aria-expanded={searchRevealed}
            aria-controls="site-header-search"
            onClick={toggleSearchReveal}
          >
            <Icon name="search" size={22} />
          </button>

          <button
            type="button"
            className="cart-link"
            aria-label={`سبد خرید (${faDigits(itemCount)} قلم)`}
            onClick={() => setCartOpen(true)}
          >
            <svg viewBox="0 0 24 24" className="cart-link__icon" aria-hidden="true">
              <path
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                d="M4 7h16l-1.5 12h-13L4 7zm4 0a4 4 0 0 1 8 0"
              />
            </svg>
            {itemCount > 0 ? (
              <span className="cart-link__badge" key={itemCount}>
                {formatPrice(itemCount)}
              </span>
            ) : null}
          </button>

          {isLoading ? null : isAuthenticated ? (
            <div className="user-menu" ref={userMenuRef}>
              {/* PR 20: icon + name on wide screens; the phone header's
                  first row and the 768-1099px tablet range show the icon
                  only (the label hides in CSS), so the button carries its
                  «حساب کاربری» name explicitly instead of relying on the
                  visible text. */}
              <button
                type="button"
                className="user-menu__trigger"
                aria-label="حساب کاربری"
                aria-expanded={userMenuOpen}
                onClick={() => setUserMenuOpen((open) => !open)}
              >
                <Icon name="user" size={20} />
                <span className="user-menu__trigger-label">
                  {user?.first_name || (user?.phone ? <bdi dir="ltr">{user.phone}</bdi> : "حساب کاربری")}
                </span>
              </button>
              {userMenuOpen ? (
                <div className="user-menu__panel">
                  <Link to="/account/" onClick={() => setUserMenuOpen(false)}>پروفایل</Link>
                  <Link to="/account/orders/" onClick={() => setUserMenuOpen(false)}>سفارش‌ها</Link>
                  <Link to="/account/addresses/" onClick={() => setUserMenuOpen(false)}>آدرس‌ها</Link>
                  <Link to="/account/reviews/" onClick={() => setUserMenuOpen(false)}>نظرات من</Link>
                  <Link to="/wishlist/" onClick={() => setUserMenuOpen(false)}>علاقه‌مندی‌ها</Link>
                  <button type="button" onClick={handleLogout}>خروج</button>
                </div>
              ) : null}
            </div>
          ) : (
            <Link
              to="/login/"
              className="btn btn--outline-light btn--sm site-header__login"
              aria-label="ورود | ثبت‌نام"
            >
              <Icon name="user" size={18} />
              <span className="site-header__login-label">ورود | ثبت‌نام</span>
            </Link>
          )}
        </div>
      </div>

      {/* The mobile navigation drawer stays portaled to body so its overlay
          and right-hand panel remain independent of the sticky header. */}
      {menuMounted ? (
        <Portal>
          <div className={`site-header__drawer${menuClosing ? " is-closing" : ""}`}>
            <div
              className="site-header__drawer-backdrop"
              aria-hidden="true"
              onClick={() => closeMenu()}
            />
            <div
              id="mobile-navigation"
              className="site-header__drawer-panel"
              role="dialog"
              aria-modal="true"
              aria-label="منوی اصلی"
              ref={drawerRef}
            >
              <div className="site-header__drawer-head">
                <button type="button" aria-label="بستن منو" onClick={() => closeMenu()}>
                  <Icon name="close" size={22} />
                </button>
              </div>
              <nav className="site-header__drawer-nav" aria-label="ناوبری اصلی">
                <NavLink
                  to="/"
                  end
                  className={({ isActive }) => `site-header__drawer-link${isActive ? " is-active" : ""}`}
                  onClick={handleHomeNavigation}
                >
                  <Icon name="home" size={20} /><span>خانه</span>
                </NavLink>
                <NavLink
                  to="/shop/"
                  end
                  className={({ isActive }) => `site-header__drawer-link${isActive ? " is-active" : ""}`}
                  onClick={() => closeMenu()}
                >
                  <Icon name="store" size={20} /><span>فروشگاه</span>
                </NavLink>
                <button
                  type="button"
                  className="site-header__drawer-link"
                  aria-haspopup="dialog"
                  aria-controls="mega-menu-sheet"
                  onClick={() => closeMenu(() => setMegaOpen(true))}
                >
                  <Icon name="grid" size={20} /><span>دسته‌بندی کالاها</span>
                  <Icon name="chevron-left" size={16} />
                </button>
                <NavLink
                  to="/wishlist/"
                  end
                  className={({ isActive }) => `site-header__drawer-link${isActive ? " is-active" : ""}`}
                  onClick={() => closeMenu()}
                >
                  <Icon name="heart" size={20} /><span>علاقه‌مندی‌ها</span>
                </NavLink>
                <NavLink
                  to="/cart/"
                  end
                  className={({ isActive }) => `site-header__drawer-link${isActive ? " is-active" : ""}`}
                  onClick={() => closeMenu()}
                >
                  <Icon name="bag" size={20} /><span>سبد خرید</span>
                </NavLink>
                <NavLink
                  to="/about/"
                  end
                  className={({ isActive }) => `site-header__drawer-link${isActive ? " is-active" : ""}`}
                  onClick={() => closeMenu()}
                >
                  <Icon name="info" size={20} /><span>دربارهٔ ما</span>
                </NavLink>
                <NavLink
                  to="/contact/"
                  end
                  className={({ isActive }) => `site-header__drawer-link${isActive ? " is-active" : ""}`}
                  onClick={() => closeMenu()}
                >
                  <Icon name="phone" size={20} /><span>تماس با ما</span>
                </NavLink>
              </nav>
              <div className="site-header__drawer-account">
                {isAuthenticated ? (
                  <>
                    <NavLink
                      to="/account/"
                      className={({ isActive }) => `site-header__drawer-link${isActive ? " is-active" : ""}`}
                      onClick={() => closeMenu()}
                    >
                      <Icon name="user" size={20} /><span>حساب کاربری</span>
                    </NavLink>
                    <button type="button" className="site-header__drawer-link" onClick={handleLogout}>
                      <Icon name="logout" size={20} /><span>خروج</span>
                    </button>
                  </>
                ) : (
                  <NavLink
                    to="/login/"
                    className={({ isActive }) => `site-header__drawer-link${isActive ? " is-active" : ""}`}
                    onClick={() => closeMenu()}
                  >
                    <Icon name="user" size={20} /><span>ورود / ثبت‌نام</span>
                  </NavLink>
                )}
              </div>
            </div>
          </div>
        </Portal>
      ) : null}

      {/* This full-viewport cart drawer shares the body portal and scroll lock
          used by the mobile navigation drawer above. */}
      {cartOpen ? (
        <Portal>
          <div className="minicart" role="dialog" aria-modal="true" aria-label="سبد خرید">
            <div className="minicart__backdrop" onClick={() => setCartOpen(false)} />
            <div className="minicart__panel" ref={minicartRef}>
              <div className="minicart__head">
                <Link
                  to="/"
                  className="minicart__brand"
                  aria-label={brandHomeLabel}
                  onClick={handleHomeNavigation}
                >
                  {/* @catalog-img-allowed: same owner brand mark in the drawer. */}
                  <img src={brandLogo} alt="" />
                  <span>{brandName}</span>
                </Link>
                <strong>سبد خرید</strong>
                <button type="button" aria-label="بستن سبد" onClick={() => setCartOpen(false)}>
                  <Icon name="close" size={20} />
                </button>
              </div>
              {cartLines.length === 0 ? (
                <p className="minicart__empty">سبد شما خالی است.</p>
              ) : (
                <>
                  <ul className="minicart__items">
                    {cartLines.map((line) => (
                      <li key={line.key}>
                        <SmartImage image={{ image: line.image }} alt="" />
                        <div className="minicart__line-body">
                          <span className="minicart__name">{faDigits(line.name)}</span>
                          {line.variant ? (
                            <span className="minicart__variant">{faDigits(line.variant)}</span>
                          ) : null}
                          <span className="minicart__unit">
                            {line.priceInfo ? (
                              <PriceTag priceInfo={line.priceInfo} size="sm" />
                            ) : (
                              "—"
                            )}
                          </span>
                        </div>
                        <div className="minicart__line-side">
                          <span className="minicart__qty">{formatPrice(line.quantity)} عدد</span>
                          <span className="minicart__line-total">
                            {line.lineTotal === null || line.lineTotal === undefined
                              ? ""
                              : `${formatPrice(line.lineTotal)} تومان`}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                  {/* Same rule as the cart page: the mini-cart shows the
                      products subtotal only -- shipping/gift wrap/final
                      amounts exist on the checkout page, not here. */}
                  <div className="minicart__subtotal">
                    <span>جمع کالاها</span>
                    <strong className="minicart__total-value">
                      {cartSubtotal === null ? "در حال محاسبه…" : `${formatPrice(cartSubtotal)} تومان`}
                    </strong>
                  </div>
                  <div className="minicart__foot">
                    <Link className="btn btn--primary" to="/cart/" onClick={() => setCartOpen(false)}>
                      مشاهدهٔ سبد و ثبت سفارش
                    </Link>
                  </div>
                </>
              )}
            </div>
          </div>
        </Portal>
      ) : null}
    </header>

    {/* PR 19: on phones the header is `position: fixed`, so it paints over
        the page instead of taking part in its flow. This spacer owns the
        header's flow height and is the ONE thing the document layout sees.
        Its height is the EXPANDED header's measured border-box height
        (PR 20: `--header-natural-height`, re-measured whenever the
        expanded two rows change size) and never changes with the
        collapsed/compact state -- that is what keeps the document height
        (and therefore scrollY) constant while the pill folds, which is
        the root-cause fix for the scroll feedback loop.
        Hidden on desktop, where the outer header stays in the flow. */}
    <div className="site-header-spacer" aria-hidden="true" />
    </>
  );
}

export default Header;
