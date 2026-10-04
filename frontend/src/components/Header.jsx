import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import { getCategoryTree, listProducts } from "../services/catalogApi";
import { formatPrice } from "../utils/formatPrice";

/**
 * Site header (Part 3 redesign): sticky + shrinks on scroll, brand
 * mark + Persian name in the display face, live search suggestions,
 * desktop mega-menu over the category tree, a clean drawer on mobile,
 * and a mini-cart drawer fed by the shared cart store (server lines or
 * guest lines hydrated from the products API).
 */
function Header() {
  const navigate = useNavigate();
  const { user, isAuthenticated, isLoading, logout, fetchMe } = useAuthStore();
  const cart = useCartStore((s) => s.cart);
  const guestLines = useCartStore((s) => s.guestLines);
  const guestProducts = useCartStore((s) => s.guestProducts);
  const fetchCart = useCartStore((s) => s.fetchCart);
  const hydrateGuestProducts = useCartStore((s) => s.hydrateGuestProducts);

  const [searchTerm, setSearchTerm] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [cartOpen, setCartOpen] = useState(false);
  const [megaCategory, setMegaCategory] = useState(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [compact, setCompact] = useState(false);
  const [categories, setCategories] = useState([]);
  const userMenuRef = useRef(null);
  const searchRef = useRef(null);
  const searchTimer = useRef(null);

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
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  // Debounced live suggestions.
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    const query = searchTerm.trim();
    if (query.length < 2) {
      setSuggestions([]);
      return undefined;
    }
    searchTimer.current = setTimeout(() => {
      listProducts({ search: query, page_size: 5 })
        .then((data) => setSuggestions(data.results || []))
        .catch(() => setSuggestions([]));
    }, 250);
    return () => clearTimeout(searchTimer.current);
  }, [searchTerm]);

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
  const cartLines = isAuthenticated
    ? (cart?.items || []).map((item) => ({
        key: item.id,
        name: item.product?.name || "",
        image: item.product?.primary_image?.image || null,
        quantity: item.quantity,
        price: item.price_info?.price ?? 0,
      }))
    : guestLines.map((line) => ({
        key: `${line.product_id}-${line.variant_id ?? 0}`,
        name: guestProducts[line.product_id]?.name || "…",
        image: guestProducts[line.product_id]?.primary_image?.image || null,
        quantity: line.quantity,
        price: guestProducts[line.product_id]?.price ?? 0,
      }));

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

        <Link to="/" className="site-header__brand" aria-label="کازین گالری — صفحه اصلی">
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
              ⌕
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
                    {product.primary_image?.image ? (
                      <img src={product.primary_image.image} alt="" />
                    ) : (
                      <span className="search-suggest__noimg" />
                    )}
                    <span className="search-suggest__name">{product.name}</span>
                    <span className="search-suggest__price">
                      {formatPrice(product.price)} تومان
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
            onMouseEnter={() => setMegaCategory(categories[0] || null)}
            onMouseLeave={() => setMegaCategory(null)}
          >
            <button type="button" className="site-header__mega-btn">
              دسته‌بندی کالاها ▾
            </button>
            {megaCategory ? (
              <div className="mega-menu" onMouseLeave={() => setMegaCategory(null)}>
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
                  <Link to={`/shop/?category=${encodeURIComponent(megaCategory.slug)}`}>
                    همهٔ {megaCategory.name}
                  </Link>
                  {(megaCategory.children || []).map((child) => (
                    <Link key={child.id} to={`/shop/?category=${encodeURIComponent(child.slug)}`}>
                      {child.name}
                    </Link>
                  ))}
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

      {menuOpen ? (
        <div className="site-header__drawer" role="dialog" aria-label="منوی اصلی">
          <div className="site-header__drawer-head">
            <span className="site-header__brand-name">کازین گالری</span>
            <button type="button" aria-label="بستن منو" onClick={() => setMenuOpen(false)}>
              ×
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
      ) : null}

      {cartOpen ? (
        <div className="minicart" role="dialog" aria-label="سبد خرید">
          <div className="minicart__backdrop" onClick={() => setCartOpen(false)} />
          <div className="minicart__panel">
            <div className="minicart__head">
              <strong>سبد خرید</strong>
              <button type="button" aria-label="بستن سبد" onClick={() => setCartOpen(false)}>
                ×
              </button>
            </div>
            {cartLines.length === 0 ? (
              <p className="minicart__empty">سبد شما خالی است.</p>
            ) : (
              <>
                <ul className="minicart__items">
                  {cartLines.map((line) => (
                    <li key={line.key}>
                      {line.image ? (
                        <img src={line.image} alt="" />
                      ) : (
                        <span className="minicart__noimg" />
                      )}
                      <span className="minicart__name">{line.name}</span>
                      <span className="minicart__qty">×{formatPrice(line.quantity)}</span>
                      <span className="minicart__price">
                        {formatPrice(line.price * line.quantity)} تومان
                      </span>
                    </li>
                  ))}
                </ul>
                <div className="minicart__foot">
                  <Link className="btn btn--primary" to="/cart/" onClick={() => setCartOpen(false)}>
                    مشاهدهٔ سبد و ثبت سفارش
                  </Link>
                </div>
              </>
            )}
          </div>
        </div>
      ) : null}
    </header>
  );
}

export default Header;
