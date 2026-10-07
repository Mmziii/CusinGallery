import { usePageMeta } from "../hooks/usePageMeta";
import PropTypes from "prop-types";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import AddressForm from "../components/AddressForm";
import { isValidIranianPhone, normalizePhone, validateAddressPayload } from "../utils/iranianFields";
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
 *
 * Part S5 item 4 ("دکمهٔ ثبت سفارش غیرفعال است"): the submit button used
 * to be disabled whenever addressMode was "saved" without a selected
 * address or "inline" without a recipient name. That ignored pickup
 * entirely (which needs only a name and a phone) and -- when the saved
 * address list failed to load or the account had none -- left the button
 * dead forever with no explanation. Now:
 *   - the button is enabled whenever an order is not being placed;
 *   - clicking it validates everything (cart, shipping method, address,
 *     pickup contact, coupon state), shows inline Persian errors next to
 *     the relevant section, scrolls to and focuses the first problem, and
 *     lists what is still missing under the button;
 *   - the default (or first) saved address and the default (or first)
 *     shipping method are selected automatically;
 *   - a failed address-list load offers a retry and never blocks ordering
 *     with a one-off address;
 *   - double submits are guarded and 429/5xx get the shared friendly
 *     wording from utils/apiError.
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

/** Order in which address fields are focused when several are missing. */
const ADDRESS_FIELD_ORDER = [
  "recipient_name",
  "phone",
  "province",
  "city",
  "address",
  "postal_code",
  "building_number",
  "unit",
];

/** A saved address is "complete" when it has the plot/unit the owner now
 *  asks for (Part S5 item 6). Older addresses stay valid -- this only
 *  drives a friendly completion prompt at checkout. */
function needsPlotAndUnit(address) {
  if (!address) return false;
  return !String(address.building_number || "").trim() || !String(address.unit || "").trim();
}

function CheckoutPage() {
  usePageMeta({ title: "تکمیل خرید", path: "/checkout/", noindex: true });
  const { cart, fetchCart } = useCartStore();

  const [addresses, setAddresses] = useState([]);
  const [addressesStatus, setAddressesStatus] = useState("loading"); // loading | ready | error
  const [addressLoadError, setAddressLoadError] = useState(null);
  const [addressMode, setAddressMode] = useState("saved"); // saved | inline
  const [selectedAddressId, setSelectedAddressId] = useState(null);
  const [showAddressForm, setShowAddressForm] = useState(false);
  const [completingAddress, setCompletingAddress] = useState(null);

  const [inlineAddress, setInlineAddress] = useState({});
  // Part S1 item 3: inline errors for the one-off checkout address,
  // validated locally before submit and merged with any server 400s.
  const [addressErrors, setAddressErrors] = useState({});

  // Shipping: the selectable methods and their costs/delivery windows all
  // come from the server (GET /orders/shipping-methods/) -- the shopper
  // only picks one; checkout recomputes everything server-side.
  const [shippingData, setShippingData] = useState(null);
  const [shippingStatus, setShippingStatus] = useState("loading"); // loading | ready | error
  const [selectedMethod, setSelectedMethod] = useState(null);
  const [pickupContact, setPickupContact] = useState({});
  const [pickupErrors, setPickupErrors] = useState({});
  const siteSettings = useSiteSettings();

  const [couponCode, setCouponCode] = useState("");
  const [couponPreview, setCouponPreview] = useState(null);
  const [couponBusy, setCouponBusy] = useState(false);
  const [couponError, setCouponError] = useState(null);

  const [placing, setPlacing] = useState(false);
  // Part S5 item 4: "what is still missing" checklist, rendered under the
  // submit button and next to the section each item belongs to.
  const [issues, setIssues] = useState([]);
  const [checkoutError, setCheckoutError] = useState(null);
  const [placedOrder, setPlacedOrder] = useState(null);
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState(null);

  // Double-submit guard: `placing` is state (async), the ref is immediate,
  // so three fast clicks can never create three orders.
  const submittingRef = useRef(false);
  // Set when a failed address load forced inline mode; a later successful
  // load switches back to the saved-address list.
  const forcedInlineRef = useRef(false);
  const addressesRef = useRef(addresses);
  addressesRef.current = addresses;

  const loadAddresses = useCallback(() => {
    setAddressesStatus("loading");
    setAddressLoadError(null);
    return authApi
      .listAddresses()
      .then((data) => {
        const list = Array.isArray(data) ? data : [];
        setAddresses(list);
        setAddressesStatus("ready");
        if (list.length === 0) {
          setAddressMode("inline");
          return;
        }
        const preferred = list.find((a) => a.is_default) || list[0];
        setSelectedAddressId((current) => current ?? preferred.id);
        if (forcedInlineRef.current) {
          forcedInlineRef.current = false;
          setAddressMode("saved");
        }
      })
      .catch((err) => {
        setAddressesStatus("error");
        setAddressLoadError(errorMessage(normalizeApiError(err)));
        // Never leave the shopper stuck: with no address list they can
        // still order with a one-off address.
        if (addressesRef.current.length === 0) {
          forcedInlineRef.current = true;
          setAddressMode("inline");
        }
      });
  }, []);

  useEffect(() => {
    fetchCart();
    loadAddresses();
    fetchShippingMethods()
      .then((data) => {
        const methods = Array.isArray(data?.methods) ? data.methods : [];
        setShippingData({ ...data, methods });
        const preferred = methods.find((m) => m.id === data?.default) || methods[0] || null;
        setSelectedMethod(preferred ? preferred.id : null);
        setShippingStatus("ready");
      })
      .catch(() => setShippingStatus("error"));
  }, [fetchCart, loadAddresses]);

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

  const methods = shippingData?.methods || [];
  const currentMethod = methods.find((m) => m.id === selectedMethod) || null;
  const isPickup = currentMethod?.requires_address === false;
  const selectedAddress = addresses.find((a) => a.id === selectedAddressId) || null;
  const selectedAddressIncomplete = needsPlotAndUnit(selectedAddress);

  /**
   * Every reason an order cannot be placed right now, as
   * { key, section, fieldId?, message } -- one source of truth for both
   * the inline errors and the checklist under the button.
   */
  const collectIssues = () => {
    const found = [];
    const push = (key, section, message, fieldId) =>
      found.push({ key, section, message, fieldId });

    if (!cart) {
      push("cart", "cart", "اطلاعات سبد خرید در حال بارگیری است؛ چند لحظه صبر کنید.", "checkout-section-cart");
    } else if (!cart.items?.length) {
      push("cart", "cart", "سبد خرید شما خالی است؛ ابتدا کالا به سبد اضافه کنید.", "checkout-section-cart");
    }

    if (addressesStatus === "loading") {
      push("addresses-loading", "address", "فهرست آدرس‌ها در حال بارگیری است؛ چند لحظه صبر کنید.", "checkout-section-address");
    }

    if (shippingStatus === "loading") {
      push("shipping-loading", "shipping", "روش‌های ارسال در حال بارگیری است؛ چند لحظه صبر کنید.", "checkout-section-shipping");
    } else if (!methods.length) {
      push("shipping-empty", "shipping", "روش ارسال در دسترس نیست؛ لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.", "checkout-section-shipping");
    } else if (!selectedMethod) {
      push("shipping-missing", "shipping", "روش ارسال را انتخاب کنید.", "checkout-section-shipping");
    }

    if (isPickup) {
      if (!String(pickupContact.recipient_name || "").trim()) {
        push("pickup-name", "address", "نام تحویل‌گیرنده را وارد کنید.", "pickup-recipient_name");
      }
      if (!String(pickupContact.phone || "").trim()) {
        push("pickup-phone", "address", "شماره تماس تحویل‌گیرنده را وارد کنید.", "pickup-phone");
      } else if (!isValidIranianPhone(pickupContact.phone)) {
        push("pickup-phone-format", "address", "شماره تماس معتبر نیست (مانند 09123456789).", "pickup-phone");
      }
    } else if (addressesStatus !== "loading") {
      if (addressMode === "saved") {
        if (!selectedAddressId) {
          push("address-missing", "address", "یک آدرس ذخیره‌شده انتخاب کنید یا آدرس جدید وارد کنید.", "checkout-section-address");
        }
      } else {
        const errors = validateAddressPayload(inlineAddress);
        const keys = ADDRESS_FIELD_ORDER.filter((key) => errors[key]);
        if (keys.length) {
          push("address-incomplete", "address", "آدرس ارسال کامل نیست؛ موارد مشخص‌شده را تکمیل کنید.", `addr-${keys[0]}`);
        }
      }
    }

    if (couponCode.trim() && !couponPreview && !couponError) {
      push("coupon-unapplied", "coupon", "کد تخفیف را وارد کرده‌اید اما اعمال نشده است؛ دکمهٔ «اعمال» را بزنید یا کد را پاک کنید.", "checkout-section-coupon");
    }

    return found;
  };

  const focusIssue = (issue) => {
    if (!issue) return;
    const el = issue.fieldId ? document.getElementById(issue.fieldId) : null;
    const target = el || document.getElementById(`checkout-section-${issue.section}`);
    if (!target) return;
    target.scrollIntoView?.({ behavior: "smooth", block: "center" });
    target.focus?.({ preventScroll: true });
  };

  const placeOrder = async () => {
    if (submittingRef.current) return;
    setCheckoutError(null);

    const found = collectIssues();
    // Inline field errors for the one-off address, so the shopper sees
    // exactly which value to fix (same rules as the server).
    if (!isPickup && addressMode === "inline") {
      setAddressErrors(validateAddressPayload(inlineAddress));
    }
    setPickupErrors({
      recipient_name: String(pickupContact.recipient_name || "").trim() ? null : "نام تحویل‌گیرنده را وارد کنید.",
      phone: !String(pickupContact.phone || "").trim()
        ? "شماره تماس را وارد کنید."
        : isValidIranianPhone(pickupContact.phone)
          ? null
          : "شماره تماس معتبر نیست (مانند 09123456789).",
    });
    setIssues(found);
    if (found.length) {
      focusIssue(found[0]);
      return;
    }

    submittingRef.current = true;
    setPlacing(true);
    try {
      const payload = isPickup
        ? { recipient_name: pickupContact.recipient_name.trim(), phone: normalizePhone(pickupContact.phone) }
        : addressMode === "saved"
          ? { address_id: selectedAddressId }
          : { ...inlineAddress };
      if (couponPreview?.code) payload.coupon_code = couponPreview.code;
      if (selectedMethod) payload.shipping_method = selectedMethod;
      const order = await checkout(payload);
      setPlacedOrder(order);
      setIssues([]);
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
      const flat = {};
      for (const [key, messages] of Object.entries(mapped)) {
        flat[key] = Array.isArray(messages) ? messages.join(" ") : String(messages);
      }
      if (addressMode === "inline" && Object.keys(flat).length > 0) {
        setAddressErrors(flat);
      }
      if (isPickup && Object.keys(flat).length > 0) setPickupErrors(flat);
      if (Object.keys(flat).length > 0 || !normalized.isNetworkError) {
        setIssues([
          {
            key: "server",
            section: isPickup ? "address" : addressMode === "saved" ? "address" : "address",
            message: normalized.message,
            fieldId: Object.keys(flat).length ? `addr-${ADDRESS_FIELD_ORDER.find((k) => flat[k])}` : undefined,
          },
        ]);
      }
      setCheckoutError(normalized);
    } finally {
      submittingRef.current = false;
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

  if (cart && cart.items.length === 0) {
    return (
      <div className="empty-state">
        <p className="empty-state__title">سبد خرید شما خالی است.</p>
        <Link className="btn btn--primary" to="/shop/">مشاهده فروشگاه</Link>
      </div>
    );
  }

  if (!cart) return <Spinner label="در حال آماده‌سازی پرداخت…" />;

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

  const sectionIssues = (section) => issues.filter((issue) => issue.section === section);
  const showPickupErrors = isPickup && issues.length > 0 ? pickupErrors : {};

  return (
    <div className="checkout">
      <h1 className="page-title">ثبت سفارش</h1>

      <CheckoutSteps current={2} done={doneSteps} />

      <div className="checkout__grid">
        <div className="checkout__main">
          {isPickup ? (
            <section
              id="checkout-section-address"
              tabIndex={-1}
              className={`checkout__section ${sectionIssues("address").length ? "checkout__section--attention" : ""}`}
            >
              <h2>دریافت حضوری</h2>
              <p className="muted">
                برای این روش، آدرس پستی لازم نیست؛ فقط نام و شمارهٔ تماس تحویل‌گیرنده:
              </p>
              <label className="field">
                <span>
                  نام تحویل‌گیرنده
                  <span className="field__required" aria-hidden="true"> *</span>
                </span>
                <input
                  id="pickup-recipient_name"
                  type="text"
                  autoComplete="name"
                  value={pickupContact.recipient_name || ""}
                  onChange={(e) => setPickupContact((f) => ({ ...f, recipient_name: e.target.value }))}
                  aria-invalid={Boolean(showPickupErrors.recipient_name)}
                  required
                />
                {showPickupErrors.recipient_name ? (
                  <span className="field__error" role="alert">{showPickupErrors.recipient_name}</span>
                ) : null}
              </label>
              <label className="field">
                <span>
                  شماره تماس
                  <span className="field__required" aria-hidden="true"> *</span>
                </span>
                <input
                  id="pickup-phone"
                  type="text"
                  dir="ltr"
                  inputMode="tel"
                  autoComplete="tel"
                  value={pickupContact.phone || ""}
                  onChange={(e) =>
                    setPickupContact((f) => ({ ...f, phone: normalizePhone(e.target.value) }))
                  }
                  aria-invalid={Boolean(showPickupErrors.phone)}
                  required
                />
                {showPickupErrors.phone ? (
                  <span className="field__error" role="alert">{showPickupErrors.phone}</span>
                ) : null}
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
          <section
            id="checkout-section-address"
            tabIndex={-1}
            className={`checkout__section ${sectionIssues("address").length ? "checkout__section--attention" : ""}`}
          >
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

            {addressesStatus === "error" ? (
              <div className="checkout__notice" role="status">
                <p>
                  فهرست آدرس‌های ذخیره‌شده بارگیری نشد
                  {addressLoadError ? `: ${addressLoadError}` : "."} می‌توانید همین حالا آدرس را دستی وارد کنید.
                </p>
                <button type="button" className="btn btn--outline btn--sm" onClick={loadAddresses}>
                  تلاش دوباره برای آدرس‌ها
                </button>
              </div>
            ) : null}

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

            {selectedAddressIncomplete && addressMode === "saved" ? (
              <div className="checkout__notice" role="status">
                <p>
                  این آدرس پلاک و واحد ندارد؛ برای ارسال دقیق‌تر آن را تکمیل کنید (برای ثبت سفارش اجباری نیست).
                </p>
                <button
                  type="button"
                  className="btn btn--outline btn--sm"
                  onClick={() => setCompletingAddress(selectedAddress)}
                >
                  تکمیل این آدرس
                </button>
              </div>
            ) : null}

            {completingAddress ? (
              <AddressForm
                initial={completingAddress}
                compact
                onSaved={(saved) => {
                  setAddresses((list) => list.map((a) => (a.id === saved.id ? saved : a)));
                  setCompletingAddress(null);
                }}
              />
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
            {sectionIssues("address").map((issue) => (
              <p key={issue.key} className="checkout__issue" role="alert">{issue.message}</p>
            ))}
          </section>
          )}

          <section
            id="checkout-section-shipping"
            tabIndex={-1}
            className={`checkout__section ${sectionIssues("shipping").length ? "checkout__section--attention" : ""}`}
          >
            <h2>روش ارسال</h2>
            {shippingStatus === "error" ? (
              <p className="checkout__issue" role="alert">
                روش‌های ارسال بارگیری نشد؛ لطفاً صفحه را دوباره بارگذاری کنید.
              </p>
            ) : null}
            {methods.length ? (
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
            ) : null}
            {currentMethod?.free_threshold && cart.subtotal < currentMethod.free_threshold ? (
              <p className="muted">
                ارسال استاندارد برای خریدهای بالای {formatPrice(currentMethod.free_threshold)} تومان رایگان است.
              </p>
            ) : null}
            {sectionIssues("shipping").map((issue) => (
              <p key={issue.key} className="checkout__issue" role="alert">{issue.message}</p>
            ))}
          </section>

          <section
            id="checkout-section-coupon"
            tabIndex={-1}
            className={`checkout__section ${sectionIssues("coupon").length ? "checkout__section--attention" : ""}`}
          >
            <h2>کد تخفیف</h2>
            <div className="coupon-row">
              <input
                type="text"
                dir="ltr"
                value={couponCode}
                placeholder="مثلاً: WELCOME10"
                onChange={(e) => {
                  setCouponCode(e.target.value);
                  setCouponError(null);
                  setCouponPreview(null);
                }}
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
            {sectionIssues("coupon").map((issue) => (
              <p key={issue.key} className="checkout__issue" role="alert">{issue.message}</p>
            ))}
          </section>
        </div>

        <aside className="checkout__summary" id="checkout-section-cart" tabIndex={-1}>
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
            disabled={placing}
          >
            {placing ? "در حال ثبت سفارش…" : "ثبت سفارش"}
          </button>
          {sectionIssues("cart").map((issue) => (
            <p key={issue.key} className="checkout__issue" role="alert">{issue.message}</p>
          ))}
          {issues.length ? (
            <ul className="checkout__checklist" aria-label="موارد ناقص">
              {issues.map((issue) => (
                <li key={issue.key}>
                  <button type="button" className="link" onClick={() => focusIssue(issue)}>
                    {issue.message}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <p className="checkout__note">مبلغ نهایی توسط سرور محاسبه و در صفحه بعد تأیید می‌شود.</p>
        </aside>
      </div>
    </div>
  );
}

export default CheckoutPage;
