import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import AddressForm from "../components/AddressForm";
import { Alert, Spinner, errorMessage } from "../components/ui";
import * as authApi from "../services/authApi";
import { checkout } from "../services/orderApi";
import { validateCoupon } from "../services/couponsApi";
import { initiatePayment } from "../services/paymentsApi";
import useCartStore from "../store/useCartStore";
import { normalizeApiError } from "../utils/apiError";
import { formatPrice } from "../utils/formatPrice";

/**
 * Checkout: choose a saved address (or enter a one-off inline address),
 * optionally apply a coupon (server-validated preview), then place the
 * order. The backend computes every total; this page only shows what the
 * server returns. After order creation the user starts payment, which
 * redirects the browser to the gateway.
 */
function CheckoutPage() {
  const { cart, fetchCart } = useCartStore();

  const [addresses, setAddresses] = useState([]);
  const [loadingAddresses, setLoadingAddresses] = useState(true);
  const [addressMode, setAddressMode] = useState("saved"); // saved | inline
  const [selectedAddressId, setSelectedAddressId] = useState(null);
  const [showAddressForm, setShowAddressForm] = useState(false);

  const [inlineAddress, setInlineAddress] = useState({});

  const [couponCode, setCouponCode] = useState("");
  const [couponPreview, setCouponPreview] = useState(null);
  const [couponBusy, setCouponBusy] = useState(false);
  const [couponError, setCouponError] = useState(null);

  const [placing, setPlacing] = useState(false);
  const [checkoutError, setCheckoutError] = useState(null);
  const [placedOrder, setPlacedOrder] = useState(null);
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState(null);

  useEffect(() => {
    fetchCart();
    setLoadingAddresses(true);
    authApi
      .listAddresses()
      .then((data) => {
        setAddresses(data);
        const defaultAddress = data.find((a) => a.is_default) || data[0];
        if (defaultAddress) setSelectedAddressId(defaultAddress.id);
        if (data.length === 0) setAddressMode("inline");
      })
      .catch(() => {})
      .finally(() => setLoadingAddresses(false));
  }, [fetchCart]);

  const applyCoupon = async () => {
    setCouponError(null);
    setCouponPreview(null);
    if (!couponCode.trim()) return;
    setCouponBusy(true);
    try {
      const result = await validateCoupon(couponCode.trim());
      setCouponPreview(result);
    } catch (err) {
      setCouponError(errorMessage(normalizeApiError(err)));
    } finally {
      setCouponBusy(false);
    }
  };

  const placeOrder = async () => {
    setCheckoutError(null);
    setPlacing(true);
    try {
      const payload =
        addressMode === "saved" ? { address_id: selectedAddressId } : { ...inlineAddress };
      if (couponPreview?.code) payload.coupon_code = couponPreview.code;
      const order = await checkout(payload);
      setPlacedOrder(order);
      // Cart is now empty server-side; refresh the badge.
      fetchCart();
    } catch (err) {
      setCheckoutError(normalizeApiError(err));
    } finally {
      setPlacing(false);
    }
  };

  const startPayment = async () => {
    setPayError(null);
    setPaying(true);
    try {
      const result = await initiatePayment(placedOrder.id);
      window.location.href = result.redirect_url;
    } catch (err) {
      setPayError(errorMessage(normalizeApiError(err)));
      setPaying(false);
    }
  };

  // --- Order placed: summary + payment start ------------------------------
  if (placedOrder) {
    return (
      <div className="checkout-done">
        <h1>سفارش شما ثبت شد</h1>
        <p>شماره سفارش: <strong>{placedOrder.order_number}</strong></p>

        <dl className="checkout-done__totals">
          <div><dt>جمع کالاها</dt><dd>{formatPrice(placedOrder.subtotal)} تومان</dd></div>
          {placedOrder.discount_amount > 0 ? (
            <div>
              <dt>تخفیف{placedOrder.coupon_code ? ` (${placedOrder.coupon_code})` : ""}</dt>
              <dd>− {formatPrice(placedOrder.discount_amount)} تومان</dd>
            </div>
          ) : null}
          <div>
            <dt>هزینه ارسال</dt>
            <dd>{placedOrder.shipping_cost === 0 ? "رایگان" : `${formatPrice(placedOrder.shipping_cost)} تومان`}</dd>
          </div>
          <div className="checkout-done__grand"><dt>مبلغ قابل پرداخت</dt><dd>{formatPrice(placedOrder.total)} تومان</dd></div>
        </dl>

        <button type="button" className="btn btn--primary" onClick={startPayment} disabled={paying}>
          {paying ? "در حال اتصال به درگاه…" : "پرداخت آنلاین"}
        </button>
        <p className="checkout-done__later">
          می‌توانید بعداً از بخش{" "}
          <Link to="/account/orders/">سفارش‌ها</Link> پرداخت را انجام دهید.
        </p>
        {payError ? <Alert>{payError}</Alert> : null}
      </div>
    );
  }

  if (loadingAddresses) return <Spinner label="در حال آماده‌سازی پرداخت…" />;

  if (!cart || cart.items.length === 0) {
    return (
      <div className="empty-state">
        <p className="empty-state__title">سبد خرید شما خالی است.</p>
        <Link className="btn btn--primary" to="/shop/">مشاهده فروشگاه</Link>
      </div>
    );
  }

  const estimatedTotal =
    cart.subtotal +
    (cart.shipping_cost_preview || 0) -
    (couponPreview ? couponPreview.discount_amount : 0);

  return (
    <div className="checkout">
      <h1>ثبت سفارش</h1>

      <div className="checkout__grid">
        <div className="checkout__main">
          <section className="checkout__section">
            <h2>آدرس ارسال</h2>

            <div className="checkout__mode-switch">
              {addresses.length > 0 ? (
                <>
                  <label>
                    <input
                      type="radio"
                      checked={addressMode === "saved"}
                      onChange={() => setAddressMode("saved")}
                    />
                    آدرس‌های ذخیره شده
                  </label>
                  <label>
                    <input
                      type="radio"
                      checked={addressMode === "inline"}
                      onChange={() => setAddressMode("inline")}
                    />
                    آدرس جدید (یک‌بار مصرف)
                  </label>
                </>
              ) : (
                <p>هیچ آدرس ذخیره‌شده‌ای ندارید؛ آدرس خود را وارد کنید یا از بخش حساب کاربری آدرس بسازید.</p>
              )}
            </div>

            {addressMode === "saved" && addresses.length > 0 ? (
              <div className="address-list">
                {addresses.map((address) => (
                  <label key={address.id} className="address-card">
                    <input
                      type="radio"
                      name="address"
                      checked={selectedAddressId === address.id}
                      onChange={() => setSelectedAddressId(address.id)}
                    />
                    <span>
                      <strong>{address.recipient_name}</strong> — {address.province}، {address.city}،{" "}
                      {address.address}
                      {address.is_default ? <em className="address-card__default">پیش‌فرض</em> : null}
                    </span>
                  </label>
                ))}
              </div>
            ) : null}

            {addressMode === "inline" ? (
              <AddressForm value={inlineAddress} onChange={setInlineAddress} compact />
            ) : (
              <button type="button" className="link" onClick={() => setShowAddressForm((v) => !v)}>
                {showAddressForm ? "بستن فرم آدرس جدید" : "+ ذخیره آدرس جدید"}
              </button>
            )}
            {showAddressForm && addressMode === "saved" ? (
              <AddressForm
                onSaved={(address) => {
                  setAddresses((list) => [...list, address]);
                  setSelectedAddressId(address.id);
                  setShowAddressForm(false);
                }}
                compact
              />
            ) : null}
          </section>

          <section className="checkout__section">
            <h2>کد تخفیف</h2>
            <div className="coupon-row">
              <input
                type="text"
                value={couponCode}
                placeholder="مثلاً: WELCOME10"
                onChange={(e) => setCouponCode(e.target.value)}
              />
              <button type="button" className="btn btn--outline" onClick={applyCoupon} disabled={couponBusy}>
                {couponBusy ? "…" : "اعمال"}
              </button>
            </div>
            {couponError ? <Alert>{couponError}</Alert> : null}
            {couponPreview ? (
              <Alert kind="success">
                کد «{couponPreview.code}» اعمال شد: {formatPrice(couponPreview.discount_amount)} تومان تخفیف.
              </Alert>
            ) : null}
          </section>
        </div>

        <aside className="checkout__summary">
          <h2>خلاصه سفارش</h2>
          <ul className="checkout__items">
            {cart.items.map((item) => (
              <li key={item.id}>
                <span>{item.product.name} × {item.quantity}</span>
                <span>{formatPrice(item.line_total)}</span>
              </li>
            ))}
          </ul>
          <dl>
            <div><dt>جمع کالاها</dt><dd>{formatPrice(cart.subtotal)} تومان</dd></div>
            <div>
              <dt>هزینه ارسال</dt>
              <dd>{cart.shipping_cost_preview === 0 ? "رایگان" : `${formatPrice(cart.shipping_cost_preview)} تومان`}</dd>
            </div>
            {couponPreview ? (
              <div><dt>تخفیف</dt><dd>− {formatPrice(couponPreview.discount_amount)} تومان</dd></div>
            ) : null}
            <div className="checkout__grand"><dt>مبلغ نهایی</dt><dd>{formatPrice(estimatedTotal)} تومان</dd></div>
          </dl>
          {checkoutError ? <Alert>{errorMessage(checkoutError)}</Alert> : null}
          <button
            type="button"
            className="btn btn--primary btn--block"
            onClick={placeOrder}
            disabled={
              placing ||
              (addressMode === "saved" && !selectedAddressId) ||
              (addressMode === "inline" && !inlineAddress.recipient_name)
            }
          >
            {placing ? "در حال ثبت سفارش…" : "ثبت سفارش"}
          </button>
          <p className="checkout__note">مبلغ نهایی توسط سرور محاسبه و در صفحه بعد تأیید می‌شود.</p>
        </aside>
      </div>
    </div>
  );
}

export default CheckoutPage;
