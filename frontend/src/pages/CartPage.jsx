import { usePageMeta } from "../hooks/usePageMeta";
import PropTypes from "prop-types";
import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";

import PriceTag from "../components/PriceTag";
import RecentlyViewed from "../components/RecentlyViewed";
import SmartImage from "../components/SmartImage";
import { Alert, EmptyState, ErrorState, Spinner, errorMessage } from "../components/ui";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import {
  lineTotalForLine,
  priceInfoForLine,
  sumLineTotals,
  unitPriceForLine,
  variantLabel,
} from "../utils/cartPricing";
import { formatPrice } from "../utils/formatPrice";
import { toast } from "../utils/toast";

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
 *
 * Part S5 follow-up 4:
 *  - item 3: prices come from `price_info` (never the nonexistent
 *    `product.price`) through the shared utils/cartPricing rule, and a line
 *    with a `variant_id` is priced from that variant's own price_info;
 *    the summary shows ONLY the products subtotal.
 *  - item 4: the items+summary grid is wrapped in `.cart-page__body` so the
 *    sticky summary can never travel over «اخیراً دیده‌اید».
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

GuestCartSkeleton.propTypes = {
  count: PropTypes.number.isRequired,
};

function GuestCartView() {
  const {
    guestLines, guestProducts, guestVariants, guestHydration, guestHydrationError,
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

  // Part S5 follow-up 4 item 3: prices come from price_info (the variant's
  // own when the line has one) -- the old `product.price` never existed in
  // the API, which is why every guest price rendered empty.
  const rows = guestLines.map((line) => {
    const product = guestProducts[line.product_id];
    const variant = line.variant_id ? guestVariants[line.variant_id] : null;
    return {
      line,
      product,
      variant,
      priceInfo: priceInfoForLine(line, product, variant),
      unitPrice: unitPriceForLine(line, product, variant),
      lineTotal: lineTotalForLine(line, product, variant),
    };
  });
  const missing = rows.filter((row) => !row.product).length;
  const fullyHydrated = missing === 0;
  const subtotal = sumLineTotals(rows.map((row) => row.lineTotal));
  const itemCount = guestLines.reduce((count, line) => count + line.quantity, 0);

  // Part S1 item 2: while product data is still loading we show skeleton
  // rows instead of half-rendered lines with a misleading 0 total.
  if (guestLines.length > 0 && !fullyHydrated && guestHydration !== "error") {
    return (
      <div className="cart-page">
        <h1 className="page-title">سبد خرید</h1>
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
      <h1 className="page-title">سبد خرید</h1>
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

      {/* Part S5 follow-up 4 item 4: the sticky summary is confined to this
          wrapper, which ends BEFORE «اخیراً دیده‌اید» -- otherwise the sticky
          box could travel down over that section (the owner's overlap). */}
      <div className="cart-page__body">
        <div className="cart-page__grid">
          <div className="cart-page__items">
            {rows.map(({ line, product, variant, priceInfo, lineTotal }) => (
              <div className="cart-item" key={`${line.product_id}-${line.variant_id ?? 0}`}>
                <SmartImage
                  image={product?.primary_image || variant?.image?.image || null}
                  alt={product?.name || ""}
                />
                <div className="cart-item__body">
                  <div className="cart-item__name">{product ? product.name : "—"}</div>
                  {variantLabel(variant) ? (
                    <div className="cart-item__variant">{variantLabel(variant)}</div>
                  ) : null}
                  <div className="cart-item__unit">
                    {priceInfo ? <PriceTag priceInfo={priceInfo} size="sm" /> : "—"}
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
                      onClick={() => {
                        // Part S2 item 6: dropping the last item removes the
                        // line -- confirm that destructive step.
                        if (line.quantity - 1 <= 0 && !window.confirm("این کالا از سبد خرید حذف شود؟")) return;
                        updateGuestItem(line.product_id, line.variant_id, line.quantity - 1);
                      }}
                    >
                      −
                    </button>
                  </div>
                </div>
                <div className="cart-item__total">
                  {lineTotal === null ? "" : `${formatPrice(lineTotal)} تومان`}
                </div>
              </div>
            ))}
          </div>

          <div className="cart-page__summary card">
            {/* Part S5 follow-up 4 item 3: the cart page shows the PRODUCTS
                subtotal and nothing else -- shipping, gift wrapping and the
                final amount belong to the checkout page. */}
            <h2>خلاصه سفارش</h2>
            <dl>
              <div>
                <dt>جمع کالاها ({formatPrice(itemCount)})</dt>
                {/* Never show a computed subtotal while some lines are unpriced. */}
                <dd>{subtotal === null ? "در حال محاسبه…" : `${formatPrice(subtotal)} تومان`}</dd>
              </div>
            </dl>
            <p className="muted">
              برای پرداخت و ثبت سفارش وارد شوید یا ثبت‌نام کنید؛ سبد شما به‌صورت خودکار منتقل
              می‌شود.
            </p>
            <div className="cart-page__actions">
              <Link className="btn btn--primary" to="/login/">ورود به حساب</Link>
              <Link className="btn btn--outline" to="/register/">ثبت‌نام</Link>
            </div>
          </div>
        </div>
      </div>

      {/* Part R5 item 10 -- outside the sticky wrapper (item 4) */}
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
      <h1 className="page-title">سبد خرید</h1>

      {/* Part S5 follow-up 4 item 4: dedicated sticky wrapper (see the guest
          view); the grid holds only the items + summary columns. */}
      <div className="cart-page__body">
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
                  <div className="cart-item__unit">
                    <PriceTag priceInfo={item.price_info} size="sm" />
                  </div>
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
                      onClick={() => {
                        if (item.quantity - 1 <= 0) {
                          if (!window.confirm("این کالا از سبد خرید حذف شود؟")) return;
                        }
                        updateItem(item.id, item.quantity - 1).then((result) => {
                          if (result && !result.success) {
                            toast(errorMessage(result.error) || "تغییر تعداد انجام نشد.", "error");
                          }
                        });
                      }}
                    >
                      −
                    </button>
                    <span>{item.quantity}</span>
                    <button
                      type="button"
                      aria-label="افزایش تعداد"
                      onClick={() => {
                        updateItem(item.id, item.quantity + 1).then((result) => {
                          if (result && !result.success) {
                            toast(errorMessage(result.error) || "تغییر تعداد انجام نشد.", "error");
                          }
                        });
                      }}
                    >
                      +
                    </button>
                  </div>
                  <div className="cart-item__total">{formatPrice(item.line_total)} تومان</div>
                  <button
                    type="button"
                    className="link-danger"
                    onClick={() => {
                      // Part S2 item 6: destructive action needs confirmation.
                      if (!window.confirm("این کالا از سبد خرید حذف شود؟")) return;
                      removeItem(item.id).then((result) => {
                        if (result && !result.success) {
                          toast(errorMessage(result.error) || "حذف انجام نشد.", "error");
                        }
                      });
                    }}
                  >
                    حذف
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Part S5 follow-up 4 item 3: unit price + line total per row, and
              below the rows ONLY the products subtotal -- no shipping, no gift
              wrapping, no final total (those are computed by the server on the
              checkout page, right before payment). */}
          <aside className="cart-page__summary">
            <h2>خلاصه سفارش</h2>
            <dl>
              <div>
                <dt>جمع کالاها ({cart.item_count})</dt>
                <dd>{formatPrice(cart.subtotal)} تومان</dd>
              </div>
            </dl>
            <button type="button" className="btn btn--primary btn--block" onClick={() => navigate("/checkout/")}>
              ادامه و ثبت سفارش
            </button>
            <p className="cart-page__note">
              مبلغ نهایی در مرحله ثبت سفارش توسط سرور محاسبه می‌شود.
            </p>
          </aside>
        </div>
      </div>

      {/* Part R5 item 10 -- outside the sticky wrapper (item 4) */}
      <RecentlyViewed />
    </div>
  );
}

export default CartPage;
