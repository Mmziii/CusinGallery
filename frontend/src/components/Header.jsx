import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import { getCategoryTree } from "../services/catalogApi";

/**
 * Site header: brand, search, primary nav, category menu, and the
 * account/cart entry points. Cart badge count reads from the shared
 * Zustand cart store so it stays in sync with every cart mutation.
 */
function Header() {
  const navigate = useNavigate();
  const { user, isAuthenticated, isLoading, logout, fetchMe } = useAuthStore();
  const cart = useCartStore((s) => s.cart);
  const fetchCart = useCartStore((s) => s.fetchCart);

  const [searchTerm, setSearchTerm] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [categories, setCategories] = useState([]);
  const userMenuRef = useRef(null);

  // Probe the session once on mount; load the cart for logged-in users.
  useEffect(() => {
    fetchMe().then(({ success }) => {
      if (success) fetchCart();
    });
    getCategoryTree()
      .then(setCategories)
      .catch(() => {});
  }, [fetchMe, fetchCart]);

  // Close the user menu on outside click.
  useEffect(() => {
    function onClick(event) {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const submitSearch = (event) => {
    event.preventDefault();
    const query = searchTerm.trim();
    navigate(query ? `/shop/?search=${encodeURIComponent(query)}` : "/shop/");
    setMenuOpen(false);
  };

  const handleLogout = async () => {
    setUserMenuOpen(false);
    await logout();
    navigate("/");
  };

  const itemCount = cart?.item_count ?? 0;

  return (
    <header className="site-header">
      <div className="container site-header__inner">
        <Link to="/" className="site-header__brand">
          کوزین <span>گالری</span>
        </Link>

        <form className="site-header__search" onSubmit={submitSearch} role="search">
          <input
            type="search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="جستجوی محصول…"
            aria-label="جستجوی محصول"
          />
          <button type="submit" className="btn btn--primary">جستجو</button>
        </form>

        <nav className="site-header__nav" aria-label="ناوبری اصلی">
          <NavLink to="/shop/" onClick={() => setMenuOpen(false)}>فروشگاه</NavLink>
          {isAuthenticated ? (
            <NavLink to="/wishlist/" onClick={() => setMenuOpen(false)}>علاقه‌مندی‌ها</NavLink>
          ) : null}
        </nav>

        <div className="site-header__actions">
          <Link to="/cart/" className="cart-link" aria-label="سبد خرید">
            <span className="cart-link__icon" aria-hidden="true">🛒</span>
            {itemCount > 0 ? <span className="cart-link__badge">{itemCount}</span> : null}
          </Link>

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
            <Link to="/login/" className="btn btn--outline btn--sm">ورود | ثبت‌نام</Link>
          )}

          <button
            type="button"
            className="site-header__burger"
            aria-label="منو"
            onClick={() => setMenuOpen((open) => !open)}
          >
            ☰
          </button>
        </div>
      </div>

      {menuOpen ? (
        <div className="site-header__mobile">
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
          ) : null}
        </div>
      ) : null}

      <div className="category-bar">
        <div className="container category-bar__inner">
          {categories.map((category) => (
            <Link key={category.id} to={`/shop/?category=${encodeURIComponent(category.slug)}`}>
              {category.name}
            </Link>
          ))}
        </div>
      </div>
    </header>
  );
}

export default Header;
