import { usePageMeta } from "../hooks/usePageMeta";
import PropTypes from "prop-types";
import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";

import RecentlyViewed from "../components/RecentlyViewed";
import SmartImage from "../components/SmartImage";
import { Alert, EmptyState, ErrorState, Spinner, errorMessage } from "../components/ui";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import { formatPrice } from "../utils/formatPrice";

const UNAVAILABLE_REASONS = {
  product_unavailable: "این محصول دیگر در دسترس نیست.",
  variant_unavailable: "این تنوع دیگر در دسترس نیست.",
  insufficient_stock: "موجودی این کالا کمتر از تعداد درخواستی است.",
};

/**
 * Guest cart view (Part 1): lines come from localStorage (ids + qty
 * only); names/prices/images are hydrated from the products API and
 * never trusted from storage. Checkout still requires an account -- on
 * login/register the store merges this cart server-side.
 */
function GuestCartSkeleton({ count }) {
  // Part S1 item 2: honest loading rows -- no fake names, no fake total.
  return (
    <div className="cart-page__items" aria-busy="true">
      {Array.from({ length: count }, (_, i) => (
        <div className="cart-item cart-item--skeleton" key={i}>
          <div className="cart-item__skeleton-img" aria-hidden="true" />
          <div className="cart-item__body">
            <div className="skeleton-line skeleton-line--lg" aria-hidden="true" />
            <div className="skeleton-line" aria-hidden="true" />
          </div>
        </div>
      ))}
      <p className="muted">در حال دریافت اطلاعات کالاها…</p>
    </div>
  );
}

function GuestCartView() {
  const {
    guestLines, guestProducts, guestHydration, guestHydrationError,
    hydrateGuestProducts, updateGuestItem,
  } = useCartStore();

  useEffect(() => {
    hydrateGuestProducts();
  }, [guestLines, hydrateGuestProducts]);

  if (guestLines.length === 0) {
    return (
      <EmptyState title="سبد خرید شما خالی است.">
        <Link className="btn btn--primary" to="/shop/">مشاهده فروشگاه</Link>
      </EmptyState>
    );
  }

  const rows = guestLines.map((line) => ({ line, product: guestProducts[line.product_id] }));
  const missing = rows.filter((row) => !row.product).length;
  const fullyHydrated = missing === 0;
  const total = rows.reduce(
    (sum, row) => sum + (row.product ? (row.product.price ?? 0) * row.line.quantity : 0),
    0
  );

  // Part S1 item 2: while product data is still loading we show skeleton
  // rows instead of half-rendered lines with a misleading 0 total.
  if (guestLines.length > 0 && !fullyHydrated && guestHydration !== "error") {
    return (
      <div className="cart-page">
        <h1>سبد خرید</h1>
        <p className="muted cart-page__guest-note">
          شما به‌صورت مهمان خرید می‌کنید؛ قیمت‌ها از سرور دریافت می‌شوند و با ورود یا ثبت‌نام،
          همین سبد به حساب شما منتقل خواهد شد.
        </p>
        <GuestCartSkeleton count={guestLines.length} />
      </div>
    );
  }

  return (
    <div className="cart-page">
      <h1>سبد خرید</h1>
      <p className="muted cart-page__guest-note">
        شما به‌صورت مهمان خرید می‌کنید؛ قیمت‌ها از سرور دریافت می‌شوند و با ورود یا ثبت‌نام،
        همین سبد به حساب شما منتقل خواهد شد.
      </p>

      {guestHydrationError && missing > 0 ? (
        <Alert>
          دریافت اطلاعات کالاها با خطا مواجه شد.
          <button type="button" className="btn btn--outline btn--sm" onClick={() => hydrateGuestProducts()}>
            تلاش دوباره
          </button>
        </Alert>
      ) : null}
      <div className="cart-page__items">
        {rows.map(({ line, product }) => (
          <div className="cart-item" key={`${line.product_id}-${line.variant_id ?? 0}`}>
            <SmartImage image={product?.primary_image || null} alt={product?.name || ""} />
            <div className="cart-item__body">
              <div className="cart-item__name">{product ? product.name : "—"}</div>
              <div className="cart-item__unit">
                {product ? `${formatPrice(product.price)} تومان` : ""}
              </div>
              <div className="cart-item__qty">
                <button
                  type="button"
                  aria-label="افزایش تعداد"
                  onClick={() => updateGuestItem(line.product_id, line.variant_id, line.quantity + 1)}
                >
                  +
                </button>
                <span>{formatPrice(line.quantity)}</span>
                <button
                  type="button"
                  aria-label="کاهش تعداد"
                  onClick={() => updateGuestItem(line.product_id, line.variant_id, line.quantity - 1)}
                >
                  −
                </button>
              </div>
            </div>
            <div className="cart-item__total">
              {product ? `${formatPrice((product.price ?? 0) * line.quantity)} تومان` : ""}
            </div>
          </div>
        ))}
      </div>
      <div className="cart-page__summary card">
        {/* Never show a computed total while some lines are unhydrated. */}
        <div className="cart-page__total">
          {fullyHydrated ? `جمع: ${formatPrice(total)} تومان` : "جمع: در حال محاسبه…"}
        </div>
        <p className="muted">
          برای پرداخت و ثبت سفارش وارد شوید یا ثبت‌نام کنید؛ سبد شما به‌صورت خودکار منتقل
          می‌شود.
        </p>
        <div className="cart-page__actions">
          <Link className="btn btn--primary" to="/login/">ورود به حساب</Link>
          <Link className="btn btn--outline" to="/register/">ثبت‌نام</Link>
        </div>
      </div>

      {/* Part R5 item 10 */}
      <RecentlyViewed />
    </div>
  );
}

function CartPage() {
  usePageMeta({ title: "سبد خرید", path: "/cart/", noindex: true });
  const navigate = useNavigate();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const { cart, isLoading, error, fetchCart, updateItem, removeItem } = useCartStore();

  useEffect(() => {
    if (!authLoading && isAuthenticated) fetchCart();
  }, [authLoading, isAuthenticated, fetchCart]);

  if (authLoading || isLoading) return <Spinner label="در حال دریافت سبد خرید…" />;

  if (!isAuthenticated) {
    return <GuestCartView />;
  }

  if (error) return <ErrorState message={errorMessage(error)} onRetry={fetchCart} />;
  if (!cart) return null;

  if (cart.items.length === 0) {
    return (
      <EmptyState title="سبد خرید شما خالی است.">
        <Link className="btn btn--primary" to="/shop/">مشاهده فروشگاه</Link>
      </EmptyState>
    );
  }

  return (
    <div className="cart-page">
      <h1>سبد خرید</h1>

      <div className="cart-page__grid">
        <div className="cart-page__items">
          {cart.items.map((item) => (
            <div key={item.id} className={`cart-item ${item.is_available ? "" : "cart-item--unavailable"}`}>
              <SmartImage image={item.product?.primary_image || null} alt={item.product?.name || ""} />

              <div className="cart-item__info">
                <Link to={`/products/${item.product.slug}/`} className="cart-item__name">
                  {item.product.name}
                </Link>
                {item.variant ? (
                  <div className="cart-item__variant">
                    {item.variant.attribute_values.map((av) => `${av.attribute}: ${av.value}`).join("، ")}
                  </div>
                ) : null}
                <div className="cart-item__unit">{formatPrice(item.price_info.price)} تومان</div>
                {!item.is_available ? (
                  <div className="cart-item__reason">
                    {UNAVAILABLE_REASONS[item.unavailable_reason] || "در دسترس نیست."}
                  </div>
                ) : null}
              </div>

              <div className="cart-item__controls">
                <div className="qty-picker">
                  <button
                    type="button"
                    aria-label="کاهش تعداد"
                    onClick={() => updateItem(item.id, item.quantity - 1)}
                  >
                    −
                  </button>
                  <span>{item.quantity}</span>
                  <button
                    type="button"
                    aria-label="افزایش تعداد"
                    onClick={() => updateItem(item.id, item.quantity + 1)}
                  >
                    +
                  </button>
                </div>
                <div className="cart-item__total">{formatPrice(item.line_total)} تومان</div>
                <button type="button" className="link-danger" onClick={() => removeItem(item.id)}>
                  حذف
                </button>
              </div>
            </div>
          ))}
        </div>

        <aside className="cart-page__summary">
          <h2>خلاصه سفارش</h2>
          <dl>
            <div>
              <dt>جمع کالاها ({cart.item_count})</dt>
              <dd>{formatPrice(cart.subtotal)} تومان</dd>
            </div>
            <div>
              <dt>هزینه ارسال</dt>
              <dd>
                {cart.shipping_cost_preview === 0 ? "رایگان" : `${formatPrice(cart.shipping_cost_preview)} تومان`}
              </dd>
            </div>
            <div className="cart-page__grand">
              <dt>مبلغ قابل پرداخت</dt>
              <dd>{formatPrice(cart.subtotal + (cart.shipping_cost_preview || 0))} تومان</dd>
            </div>
          </dl>
          <button type="button" className="btn btn--primary btn--block" onClick={() => navigate("/checkout/")}>
            ادامه و ثبت سفارش
          </button>
          <p className="cart-page__note">
            هزینه ارسال و تخفیف نهایی در مرحله ثبت سفارش توسط سرور محاسبه می‌شود.
          </p>
        </aside>
      </div>

      {/* Part R5 item 10 */}
      <RecentlyViewed />
    </div>
  );
}

GuestCartSkeleton.propTypes = { count: PropTypes.number.isRequired };

export default CartPage;
