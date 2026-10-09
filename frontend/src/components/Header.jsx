import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";

import Icon from "./Icon";
import Portal from "./Portal";
import PriceTag from "./PriceTag";
import SmartImage from "./SmartImage";
import useFocusTrap from "../hooks/useFocusTrap";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import { getCategoryTree, listProducts } from "../services/catalogApi";
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
  const location = useLocation();
  const navigate = useNavigate();
  const { user, isAuthenticated, isLoading, logout, fetchMe } = useAuthStore();
  const cart = useCartStore((s) => s.cart);
  const guestLines = useCartStore((s) => s.guestLines);
  const guestProducts = useCartStore((s) => s.guestProducts);
  const guestVariants = useCartStore((s) => s.guestVariants);
  const fetchCart = useCartStore((s) => s.fetchCart);
  const hydrateGuestProducts = useCartStore((s) => s.hydrateGuestProducts);

  const [searchTerm, setSearchTerm] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [cartOpen, setCartOpen] = useState(false);
  const [megaOpen, setMegaOpen] = useState(false);
  const [megaCategory, setMegaCategory] = useState(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [compact, setCompact] = useState(false);
  const [categories, setCategories] = useState([]);
  const userMenuRef = useRef(null);
  const searchRef = useRef(null);
  const searchTimer = useRef(null);
  // A response can arrive after the shopper has used the home brand action.
  // Versioning prevents that stale response from reopening suggestions.
  const searchRequestVersion = useRef(0);
  const megaRef = useRef(null);
  const megaCloseTimer = useRef(null);
  const drawerRef = useRef(null);
  const minicartRef = useRef(null);

  // Part S2 item 8: focus trap + Escape + focus restore for the two
  // full drawers (mobile menu, mini-cart). The hover-driven mega menu
  // intentionally stays trap-free; it handles Escape below and returns
  // focus to its trigger.
  useFocusTrap(drawerRef, menuOpen, () => setMenuOpen(false));
  useFocusTrap(minicartRef, cartOpen, () => setCartOpen(false));

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

  // Sticky shrink.
  useEffect(() => {
    const onScroll = () => setCompact(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
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
      if (megaRef.current && !megaRef.current.contains(event.target)) {
        setMegaOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // Mega menu (Part R1): hover-intent open/close. The panel is a DOM child of
  // the trigger wrapper and its CSS adds an invisible padding bridge, so the
  // pointer never "leaves" while crossing the visual gap; closing is further
  // delayed ~200 ms and cancelled when the pointer re-enters trigger OR panel.
  // Click/keyboard (Enter/Space on the button) toggles it for touch devices;
  // Escape closes.
  const cancelMegaClose = () => {
    if (megaCloseTimer.current) {
      clearTimeout(megaCloseTimer.current);
      megaCloseTimer.current = null;
    }
  };
  const megaBtnRef = useRef(null);
  const megaFocusPending = useRef(false);
  const openMega = () => {
    cancelMegaClose();
    setMegaOpen(true);
    setMegaCategory((current) => current || categories[0] || null);
  };
  const closeMega = () => {
    cancelMegaClose();
    setMegaOpen(false);
  };
  const scheduleMegaClose = () => {
    cancelMegaClose();
    megaCloseTimer.current = setTimeout(() => setMegaOpen(false), 200);
  };
  useEffect(() => () => cancelMegaClose(), []);

  useEffect(() => {
    if (!megaOpen) return undefined;
    function onKey(event) {
      if (event.key === "Escape") {
        setMegaOpen(false);
        // Part S2 item 8: focus restore for keyboard users.
        megaBtnRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [megaOpen]);

  // Part S2 item 8: when the mega menu was opened by CLICK/keyboard (not
  // hover), move focus to the first category so Tab users land inside.
  useEffect(() => {
    if (!megaOpen || !megaFocusPending.current) return;
    megaFocusPending.current = false;
    const first = megaRef.current?.querySelector(".mega-menu__roots button");
    if (first) first.focus();
  }, [megaOpen, megaCategory]);

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
    cancelMegaClose();
    megaFocusPending.current = false;
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchRequestVersion.current += 1;
    setMenuOpen(false);
    setCartOpen(false);
    setMegaOpen(false);
    setUserMenuOpen(false);
    setSuggestions([]);
    setSearchTerm("");
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
    setMenuOpen(false);
    navigate(query ? `/shop/?search=${encodeURIComponent(query)}` : "/shop/");
  };

  const handleLogout = async () => {
    setUserMenuOpen(false);
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

  return (
    <header className={`site-header ${compact ? "site-header--compact" : ""}`}>
      <div className="container site-header__inner">
        <button
          type="button"
          className="site-header__burger"
          aria-label="بازکردن منو"
          onClick={() => setMenuOpen((open) => !open)}
        >
          <span />
          <span />
          <span />
        </button>

        <Link
          to="/"
          className="site-header__brand"
          aria-label="کازین گالری — صفحه اصلی"
          onClick={handleHomeNavigation}
        >
          <img src="/brand/logo-gold.svg" alt="" className="site-header__logo" />
          <span className="site-header__brand-name">کازین گالری</span>
        </Link>

        <div className="site-header__search" ref={searchRef} role="search">
          <form onSubmit={submitSearch}>
            <input
              type="search"
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
                    <span className="search-suggest__name">{product.name}</span>
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

        <nav className="site-header__nav" aria-label="ناوبری اصلی">
          <div
            className="site-header__mega-trigger"
            ref={megaRef}
            onMouseEnter={openMega}
            onMouseLeave={scheduleMegaClose}
          >
            <button
              type="button"
              className="site-header__mega-btn"
              ref={megaBtnRef}
              aria-haspopup="true"
              aria-expanded={megaOpen}
              onClick={() => {
                if (megaOpen) {
                  closeMega();
                } else {
                  megaFocusPending.current = true;
                  openMega();
                }
              }}
            >
              دسته‌بندی کالاها
              <Icon name="chevron-down" size={16} />
            </button>
            {megaOpen && megaCategory ? (
              <div className="mega-menu">
                <div className="mega-menu__inner">
                  <ul className="mega-menu__roots">
                    {categories.map((category) => (
                      <li key={category.id}>
                        <button
                          type="button"
                          className={megaCategory?.id === category.id ? "is-active" : ""}
                          onMouseEnter={() => setMegaCategory(category)}
                        >
                          {category.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className="mega-menu__panel">
                    <Link to={`/shop/?category=${encodeURIComponent(megaCategory.slug)}`} onClick={closeMega}>
                      همهٔ {megaCategory.name}
                    </Link>
                    {(megaCategory.children || []).map((child) => (
                      <Link key={child.id} to={`/shop/?category=${encodeURIComponent(child.slug)}`} onClick={closeMega}>
                        {child.name}
                      </Link>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
          <NavLink to="/shop/">فروشگاه</NavLink>
          {isAuthenticated ? <NavLink to="/wishlist/">علاقه‌مندی‌ها</NavLink> : null}
        </nav>

        <div className="site-header__actions">
          <button
            type="button"
            className="cart-link"
            aria-label={`سبد خرید (${itemCount} قلم)`}
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
                {user?.first_name || user?.phone || "حساب کاربری"}
              </button>
              {userMenuOpen ? (
                <div className="user-menu__panel">
                  <Link to="/account/" onClick={() => setUserMenuOpen(false)}>پروفایل</Link>
                  <Link to="/account/orders/" onClick={() => setUserMenuOpen(false)}>سفارش‌ها</Link>
                  <Link to="/account/addresses/" onClick={() => setUserMenuOpen(false)}>آدرس‌ها</Link>
                  <button type="button" onClick={handleLogout}>خروج</button>
                </div>
              ) : null}
            </div>
          ) : (
            <Link to="/login/" className="btn btn--outline-light btn--sm">ورود | ثبت‌نام</Link>
          )}
        </div>
      </div>

      {/* Part S5 follow-up 4: portal -- a position: fixed drawer must not live
          inside the header, because the scrolled header's backdrop-filter makes
          it the containing block and shrinks the drawer to the header's box. */}
      {menuOpen ? (
        <Portal>
          <div className="site-header__drawer" role="dialog" aria-modal="true" aria-label="منوی اصلی" ref={drawerRef}>
            <div className="site-header__drawer-head">
              <Link
                to="/"
                className="site-header__brand site-header__drawer-brand"
                aria-label="کازین گالری — صفحه اصلی"
                onClick={handleHomeNavigation}
              >
                <img src="/brand/logo-gold.svg" alt="" className="site-header__logo" />
                <span className="site-header__brand-name">کازین گالری</span>
              </Link>
              <button type="button" aria-label="بستن منو" onClick={() => setMenuOpen(false)}>
                <Icon name="close" size={22} />
              </button>
            </div>
            <NavLink to="/" onClick={() => setMenuOpen(false)}>خانه</NavLink>
            <NavLink to="/shop/" onClick={() => setMenuOpen(false)}>فروشگاه</NavLink>
            {categories.map((category) => (
              <NavLink
                key={category.id}
                to={`/shop/?category=${encodeURIComponent(category.slug)}`}
                onClick={() => setMenuOpen(false)}
              >
                {category.name}
              </NavLink>
            ))}
            {isAuthenticated ? (
              <NavLink to="/wishlist/" onClick={() => setMenuOpen(false)}>علاقه‌مندی‌ها</NavLink>
            ) : (
              <NavLink to="/login/" onClick={() => setMenuOpen(false)}>ورود | ثبت‌نام</NavLink>
            )}
          </div>
        </Portal>
      ) : null}

      {/* Part S5 follow-up 4: portal (see the mobile drawer above) -- this is
          the drawer the owner saw truncated to the header's height while the
          page was scrolled. */}
      {cartOpen ? (
        <Portal>
          <div className="minicart" role="dialog" aria-modal="true" aria-label="سبد خرید">
            <div className="minicart__backdrop" onClick={() => setCartOpen(false)} />
            <div className="minicart__panel" ref={minicartRef}>
              <div className="minicart__head">
                <Link
                  to="/"
                  className="minicart__brand"
                  aria-label="کازین گالری — صفحه اصلی"
                  onClick={handleHomeNavigation}
                >
                  <img src="/brand/logo-gold.svg" alt="" />
                  <span>کازین گالری</span>
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
                          <span className="minicart__name">{line.name}</span>
                          {line.variant ? (
                            <span className="minicart__variant">{line.variant}</span>
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
