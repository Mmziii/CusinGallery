import { usePageMeta } from "../hooks/usePageMeta";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import AddressForm from "../components/AddressForm";
import { normalizePhone, validateAddressPayload } from "../utils/iranianFields";
import { Alert, Spinner, errorMessage } from "../components/ui";
import * as authApi from "../services/authApi";
import { checkout, fetchShippingMethods } from "../services/orderApi";
import { validateCoupon } from "../services/couponsApi";
import { initiatePayment } from "../services/paymentsApi";
import useCartStore from "../store/useCartStore";
import useSiteSettings from "../hooks/useSiteSettings";
import { normalizeApiError } from "../utils/apiError";
import { formatPrice } from "../utils/formatPrice";

/**
 * Checkout: choose a saved address (or enter a one-off inline address),
 * optionally apply a coupon (server-validated preview), then place the
 * order. The backend computes every total; this page only shows what the
 * server returns. After order creation the user starts payment, which
 * redirects the browser to the gateway.
 */
const METHOD_LABELS = {
  standard: "ارسال عادی",
  express: "ارسال اکسپرس",
  pickup: "دریافت حضوری",
};

/** Persian display name for a method id; unknown ids render as-is. */
function methodLabel(id) {
  return METHOD_LABELS[id] || id;
}

/**
 * Part S2 item 6: checkout progress indicator (address -> shipping ->
 * review -> payment). `done` marks completed steps, `current` the active
 * one; everything is visible on mobile too (horizontal wrap).
 */
function CheckoutSteps({ done, current }) {
  const labels = ["آدرس", "روش ارسال", "بازبینی", "پرداخت"];
  return (
    <ol className="checkout__steps" aria-label="مراحل ثبت سفارش">
      {labels.map((label, index) => {
        const isDone = index < current || (done || []).includes(index);
        const isCurrent = index === current;
        return (
          <li
            key={label}
            className={`checkout__step ${isDone ? "checkout__step--done" : ""} ${
              isCurrent ? "checkout__step--current" : ""
            }`}
            aria-current={isCurrent ? "step" : undefined}
          >
            <span className="checkout__step-num" aria-hidden="true">{formatPrice(index + 1)}</span>
            {label}
          </li>
        );
      })}
    </ol>
  );
}

CheckoutSteps.propTypes = {
  current: PropTypes.number.isRequired,
  done: PropTypes.arrayOf(PropTypes.number),
};

/** Server-configured cost of a method for a given subtotal -- the same
 *  free-threshold rule the backend applies (see apps/orders/shipping.py);
 *  used only for the on-page preview, never for the real charge. */
function methodCostFor(method, subtotal) {
  if (method.free_threshold != null && subtotal >= method.free_threshold) return 0;
  return method.cost;
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString("fa-IR");
}

function CheckoutPage() {
  usePageMeta({ title: "تکمیل خرید", path: "/checkout/", noindex: true });
  const { cart, fetchCart } = useCartStore();

  const [addresses, setAddresses] = useState([]);
  const [loadingAddresses, setLoadingAddresses] = useState(true);
  const [addressMode, setAddressMode] = useState("saved"); // saved | inline
  const [selectedAddressId, setSelectedAddressId] = useState(null);
  const [showAddressForm, setShowAddressForm] = useState(false);

  const [inlineAddress, setInlineAddress] = useState({});
  // Part S1 item 3: inline errors for the one-off checkout address,
  // validated locally before submit and merged with any server 400s.
  const [addressErrors, setAddressErrors] = useState({});

  // Shipping: the selectable methods and their costs/delivery windows all
  // come from the server (GET /orders/shipping-methods/) -- the shopper
  // only picks one; checkout recomputes everything server-side.
  const [shippingData, setShippingData] = useState(null);
  const [selectedMethod, setSelectedMethod] = useState(null);
  const [pickupContact, setPickupContact] = useState({});
  const siteSettings = useSiteSettings();

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
    fetchShippingMethods()
      .then((data) => {
        setShippingData(data);
        setSelectedMethod(data.default);
      })
      .catch(() => {});
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
      const isPickupNow =
        (shippingData?.methods || []).find((m) => m.id === selectedMethod)?.requires_address === false;
      if (!isPickupNow && addressMode === "inline") {
        const errors = validateAddressPayload(inlineAddress);
        if (Object.keys(errors).length > 0) {
          setAddressErrors(errors);
          const firstKey = ["recipient_name", "phone", "province", "city", "address", "postal_code"]
            .find((key) => errors[key]);
          document.getElementById(`addr-${firstKey}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
          document.getElementById(`addr-${firstKey}`)?.focus({ preventScroll: true });
          return;
        }
      }
      const payload = isPickupNow
        ? { recipient_name: pickupContact.recipient_name, phone: pickupContact.phone }
        : addressMode === "saved"
          ? { address_id: selectedAddressId }
          : { ...inlineAddress };
      if (couponPreview?.code) payload.coupon_code = couponPreview.code;
      if (selectedMethod) payload.shipping_method = selectedMethod;
      const order = await checkout(payload);
      setPlacedOrder(order);
      // Cart is now empty server-side; refresh the badge.
      fetchCart();
    } catch (err) {
      const normalized = normalizeApiError(err);
      // Server-side address rejections map straight onto the inline form
      // fields so the customer sees WHICH value to fix.
      const apiFieldErrors = normalized.fieldErrors || {};
      const addressKeys = ["recipient_name", "phone", "province", "city", "address", "postal_code", "unit", "building_number"];
      const mapped = Object.fromEntries(
        Object.entries(apiFieldErrors).filter(([key]) => addressKeys.includes(key))
      );
      if (addressMode === "inline" && Object.keys(mapped).length > 0) {
        const flat = {};
        for (const [key, messages] of Object.entries(mapped)) {
          flat[key] = Array.isArray(messages) ? messages.join(" ") : String(messages);
        }
        setAddressErrors(flat);
      }
      setCheckoutError(normalized);
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
        <CheckoutSteps current={3} done={[0, 1, 2]} />
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
            <dt>هزینه ارسال ({methodLabel(placedOrder.shipping_method)})</dt>
            <dd>{placedOrder.shipping_cost === 0 ? "رایگان" : `${formatPrice(placedOrder.shipping_cost)} تومان`}</dd>
          </div>
          <div className="checkout-done__grand"><dt>مبلغ قابل پرداخت</dt><dd>{formatPrice(placedOrder.total)} تومان</dd></div>
        </dl>

        {placedOrder.estimated_delivery_min && placedOrder.estimated_delivery_max ? (
          <p className="checkout-done__later">
            تحویل تخمینی: {formatDate(placedOrder.estimated_delivery_min)} تا{" "}
            {formatDate(placedOrder.estimated_delivery_max)}
          </p>
        ) : null}

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

  const methods = shippingData?.methods || [];
  const currentMethod = methods.find((m) => m.id === selectedMethod) || null;

  // Part S2 item 6: which early steps already count as done, so the
  // progress indicator reflects real completion (not just position).
  const needsAddress = currentMethod ? currentMethod.requires_address !== false : true;
  const addressDone = !needsAddress
    ? Boolean((pickupContact.recipient_name || "").trim() && (pickupContact.phone || "").trim())
    : addressMode === "saved"
      ? Boolean(selectedAddressId)
      : Object.keys(validateAddressPayload(inlineAddress)).length === 0;
  const doneSteps = [
    ...(addressDone ? [0] : []),
    ...(addressDone && selectedMethod ? [1] : []),
  ];
  const previewedShippingCost = currentMethod ? methodCostFor(currentMethod, cart.subtotal) : (cart.shipping_cost_preview || 0);

  const estimatedTotal =
    cart.subtotal +
    previewedShippingCost -
    (couponPreview ? couponPreview.discount_amount : 0);

  return (
    <div className="checkout">
      <h1>ثبت سفارش</h1>

      <CheckoutSteps current={2} done={doneSteps} />

      <div className="checkout__grid">
        <div className="checkout__main">
          {currentMethod?.requires_address === false ? (
            <section className="checkout__section">
              <h2>دریافت حضوری</h2>
              <p className="muted">
                برای این روش، آدرس پستی لازم نیست؛ فقط نام و شمارهٔ تماس تحویل‌گیرنده:
              </p>
              <label className="field">
                <span>نام تحویل‌گیرنده</span>
                <input
                  type="text"
                  autoComplete="name"
                  value={pickupContact.recipient_name || ""}
                  onChange={(e) => setPickupContact((f) => ({ ...f, recipient_name: e.target.value }))}
                  required
                />
              </label>
              <label className="field">
                <span>شماره تماس</span>
                <input
                  type="text"
                  dir="ltr"
                  inputMode="tel"
                  autoComplete="tel"
                  value={pickupContact.phone || ""}
                  onChange={(e) =>
                    setPickupContact((f) => ({ ...f, phone: normalizePhone(e.target.value) }))
                  }
                  required
                />
              </label>
              {siteSettings.pickup_address ? (
                <p className="checkout__pickup-info">
                  <strong>نشانی دریافت:</strong> {siteSettings.pickup_address}
                  {siteSettings.pickup_hours ? (
                    <>
                      <br />
                      <strong>ساعات دریافت:</strong> {siteSettings.pickup_hours}
                    </>
                  ) : null}
                </p>
              ) : null}
            </section>
          ) : (
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
              <AddressForm
                value={inlineAddress}
                onChange={(next) => {
                  setInlineAddress(next);
                  if (Object.keys(addressErrors).length) setAddressErrors({});
                }}
                fieldErrors={addressErrors}
                compact
              />
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
          )}

          {methods.length ? (
            <section className="checkout__section">
              <h2>روش ارسال</h2>
              <div className="shipping-methods">
                {methods.map((method) => {
                  const cost = methodCostFor(method, cart.subtotal);
                  return (
                    <label
                      key={method.id}
                      className={
                        selectedMethod === method.id
                          ? "shipping-method shipping-method--active"
                          : "shipping-method"
                      }
                    >
                      <input
                        type="radio"
                        name="shipping_method"
                        checked={selectedMethod === method.id}
                        onChange={() => setSelectedMethod(method.id)}
                      />
                      <span className="shipping-method__body">
                        <strong>{method.label || methodLabel(method.id)}</strong>
                        <span className="muted">
                          {method.requires_address === false
                            ? "آمادهٔ تحویل حضوری پس از پرداخت"
                            : method.min_days === method.max_days
                              ? `تحویل ${method.min_days} روزه`
                              : `تحویل ${method.min_days} تا ${method.max_days} روز کاری`}
                        </span>
                      </span>
                      <span className="shipping-method__cost">
                        {cost === 0 ? "رایگان" : `${formatPrice(cost)} تومان`}
                      </span>
                    </label>
                  );
                })}
              </div>
              {currentMethod?.free_threshold && cart.subtotal < currentMethod.free_threshold ? (
                <p className="muted">
                  ارسال استاندارد برای خریدهای بالای {formatPrice(currentMethod.free_threshold)} تومان رایگان است.
                </p>
              ) : null}
            </section>
          ) : null}

          <section className="checkout__section">
            <h2>کد تخفیف</h2>
            <div className="coupon-row">
              <input
                type="text"
                dir="ltr"
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
              <dt>هزینه ارسال{currentMethod ? ` (${methodLabel(currentMethod.id)})` : ""}</dt>
              <dd>{previewedShippingCost === 0 ? "رایگان" : `${formatPrice(previewedShippingCost)} تومان`}</dd>
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
