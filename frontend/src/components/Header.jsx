import { faDigits } from "../utils/faDigits";
import useWishlistStore from "../store/useWishlistStore";
import { useCallback, useEffect, useRef, useState } from "react";
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
import { isDesktopViewport } from "../utils/viewport";
import {
  lineTotalForLine,
  priceInfoForLine,
  sumLineTotals,
  unitPriceForLine,
  variantLabel,
} from "../utils/cartPricing";
import { formatPrice } from "../utils/formatPrice";

/**
 * Site header (Part 3 redesign): sticky + shrinks on scroll, brand
 * mark + Persian name in the display face, live search suggestions,
 * desktop mega-menu over the category tree, a clean drawer on mobile,
 * and a mini-cart drawer fed by the shared cart store (server lines or
 * guest lines hydrated from the products API).
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
  const [compact, setCompact] = useState(false);
  // Phone only: the wrapped header (~245px: brand + categories +
  // account/cart + search rows) folds into one row once the shopper has
  // scrolled past 80px and is still going down. Scrolling up by 24px --
  // or reaching the top -- restores it.
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

  // Audit 19: publish the header's REAL height as --site-header-height.
  // Sticky elements that must sit directly under it (the shop's mobile
  // filter/sort bar, the gallery) used to hard-code 76px, which is wrong the
  // moment the phone layout wraps the search onto a second row.
  //
  // The same pass publishes --header-natural-height: the EXPANDED inner
  // height the phone collapse transitions to/from. CSS cannot interpolate
  // to/from `height: auto`, so the value has to be measured -- and the one
  // bug that must never come back is publishing a measurement taken while
  // the header was folded or mid-animation (the phone shrink runs 200ms and
  // the compact shrink changes the logo height). A stale, too-small value
  // pins the header box below its content, which then paints over the page.
  //
  // Therefore:
  //   * the natural height is measured ONLY while the header is fully
  //     expanded (!rowCollapsed) AND not shrinking (!compact) AND not
  //     animating -- otherwise the frame is skipped;
  //   * `scrollHeight` (the content height) is preferred over `offsetHeight`
  //     (the box height), so even a frame caught mid-transition reads the
  //     real content, never an interpolated box;
  //   * a ResizeObserver watches the expanded inner, so wrapped rows, font
  //     swaps and orientation changes re-measure on their own;
  //   * it re-measures on resize/orientationchange, after webfonts load and
  //     once the height transition ends.
  // The rendered header is also a sticky element that keeps its real height
  // in the flow, so page content can never slide underneath it.
  useEffect(() => {
    const root = document.documentElement;
    let frame = null;
    // The refs are updated by the rAF-throttled scroll pass, which may run
    // one frame after this one; the live offset closes that gap, so a
    // measurement can never be taken while the header is compact or folded.
    const naturalCanBeMeasured = () =>
      (window.scrollY || 0) <= 24 &&
      !rowCollapsedRef.current &&
      !compactRef.current &&
      !animatingRef.current;

    const measure = () => {
      frame = null;
      const header = headerRef.current;
      const inner = innerRef.current;
      if (!header || !inner) return;
      const height = header.offsetHeight || 0;
      // jsdom and hidden tabs report 0 -- keep the last real value instead
      // of pinning every sticky offset to 0.
      if (height > 0) root.style.setProperty("--site-header-height", `${height}px`);
      if (!naturalCanBeMeasured()) return;
      // Content height first: when the inner is height-constrained (folded,
      // searching or animating) scrollHeight still describes the content,
      // while offsetHeight describes the animation frame.
      const natural = Math.max(inner.scrollHeight || 0, inner.offsetHeight || 0);
      // `auto` (no variable) is always correct, so only publish real
      // measurements -- a 0 must never overwrite a good value.
      if (natural > 0) root.style.setProperty("--header-natural-height", `${natural}px`);
    };
    const schedule = () => {
      if (frame !== null) return;
      frame = window.requestAnimationFrame ? window.requestAnimationFrame(measure) : measure();
    };
    // A width/orientation change invalidates the measurement (rows wrap
    // differently): drop back to `auto` -- always safe, never clips -- and
    // re-measure on the next frame.
    const onViewportChange = () => {
      if (!rowCollapsedRef.current) root.style.removeProperty("--header-natural-height");
      schedule();
    };
    schedule();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", onViewportChange);
    window.addEventListener("orientationchange", onViewportChange);
    const resizeObserver =
      typeof ResizeObserver === "function" ? new ResizeObserver(schedule) : null;
    if (resizeObserver && innerRef.current) resizeObserver.observe(innerRef.current);
    // Webfonts change the Persian line boxes; re-measure once they are in.
    const fonts = typeof document !== "undefined" ? document.fonts : null;
    if (fonts?.ready?.then) fonts.ready.then(schedule).catch(() => {});
    return () => {
      if (frame !== null && window.cancelAnimationFrame) window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", onViewportChange);
      window.removeEventListener("orientationchange", onViewportChange);
      resizeObserver?.disconnect();
    };
  }, []);

  // Sticky shrink + the phone one-row collapse.
  //
  // `compact` is the long-standing shrink every viewport gets past 24px
  // (smaller logo, shorter bar). `rowCollapsed` is phone-only and needs the
  // scroll DIRECTION, a travel threshold and an offset: past 80px, with 24px
  // of cumulative downward travel, the header folds; 24px of upward travel --
  // or reaching the top (<= 10px) -- restores it. The two thresholds are the
  // hysteresis: rubber-banding and the tail of a smooth scroll never flicker
  // the height, but a deliberate swipe up always brings the full header back.
  // The listener is rAF-throttled: at most one state pass per frame.
  useEffect(() => {
    const TOP_ZONE = 10;
    const COMPACT_AT = 24;
    const COLLAPSE_AT = 80;
    const COLLAPSE_TRAVEL = 24;
    const EXPAND_TRAVEL = 24;
    let lastY = window.scrollY || 0;
    let downTravel = 0;
    let upTravel = 0;
    let frame = null;

    const collapseRow = () => {
      rowCollapsedRef.current = true;
      // Folding with the search row open would keep the inner tall.
      searchRevealedRef.current = false;
      setSearchRevealed(false);
      setRowCollapsed(true);
    };
    const expandRow = () => {
      rowCollapsedRef.current = false;
      setRowCollapsed(false);
    };

    const evaluate = () => {
      frame = null;
      const y = window.scrollY || 0;
      const delta = y - lastY;
      lastY = y;

      const isCompact = y > COMPACT_AT;
      compactRef.current = isCompact;
      setCompact(isCompact);

      if (y <= TOP_ZONE) {
        downTravel = 0;
        upTravel = 0;
        if (rowCollapsedRef.current) expandRow();
        if (searchRevealedRef.current) {
          searchRevealedRef.current = false;
          setSearchRevealed(false);
        }
        return;
      }

      if (delta > 0) {
        downTravel += delta;
        upTravel = 0;
        // A downward jitter must not re-fold a header the shopper just
        // opened with an upward swipe.
        if (!rowCollapsedRef.current && y > COLLAPSE_AT && downTravel >= COLLAPSE_TRAVEL) {
          collapseRow();
        }
      } else if (delta < 0) {
        upTravel += -delta;
        downTravel = 0;
        if (rowCollapsedRef.current && upTravel >= EXPAND_TRAVEL) expandRow();
      }
    };

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
      if (frame === null) return;
      if (window.cancelAnimationFrame) window.cancelAnimationFrame(frame);
      else window.clearTimeout(frame);
    };
  }, []);

  // Track the inner's height transition so the measurement pass above can
  // skip the interpolated frames and then re-measure at rest.
  useEffect(() => {
    const inner = innerRef.current;
    if (!inner) return undefined;
    const onTransitionStart = (event) => {
      if (event.propertyName === "height") animatingRef.current = true;
    };
    const onTransitionEnd = (event) => {
      if (event.propertyName && event.propertyName !== "height") return;
      animatingRef.current = false;
      if (!rowCollapsedRef.current && !compactRef.current) {
        const natural = Math.max(inner.scrollHeight || 0, inner.offsetHeight || 0);
        if (natural > 0) {
          document.documentElement.style.setProperty("--header-natural-height", `${natural}px`);
        }
      }
    };
    inner.addEventListener("transitionstart", onTransitionStart);
    inner.addEventListener("transitionend", onTransitionEnd);
    inner.addEventListener("transitioncancel", onTransitionEnd);
    return () => {
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

  const headerClass = [
    "site-header",
    compact && "site-header--compact",
    rowCollapsed && "site-header--collapsed",
    rowCollapsed && searchRevealed && "site-header--searching",
  ]
    .filter(Boolean)
    .join(" ");

  return (
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

        {/* Stage 2: the trigger lives OUTSIDE .site-header__nav
            (which phones hide) so «دسته‌بندی کالاها» is
            reachable on every screen size. */}
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
              <button
                type="button"
                className="user-menu__trigger"
                onClick={() => setUserMenuOpen((open) => !open)}
              >
                {user?.first_name || (user?.phone ? <bdi dir="ltr">{user.phone}</bdi> : "حساب کاربری")}
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
            <Link to="/login/" className="btn btn--outline-light btn--sm">ورود | ثبت‌نام</Link>
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
  );
}

export default Header;
