import { formatAddress } from "../utils/formatAddress";
import { faDigits, deliveryRange, deliveryDays, hoursRange } from "../utils/faDigits";
import { usePageMeta } from "../hooks/usePageMeta";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import AddressForm from "../components/AddressForm";
import CheckoutStepper from "../components/CheckoutStepper";
import Icon from "../components/Icon";
import SmartImage from "../components/SmartImage";
import { isValidIranianPhone, normalizePhone, validateAddressPayload } from "../utils/iranianFields";
import { Alert, Spinner, errorMessage } from "../components/ui";
import * as authApi from "../services/authApi";
import { checkout, fetchShippingMethods } from "../services/orderApi";
import { trackEvent } from "../utils/behaviour";
import { validateCoupon } from "../services/couponsApi";
import { initiatePayment } from "../services/paymentsApi";
import useCartStore from "../store/useCartStore";
import useSiteSettings from "../hooks/useSiteSettings";
import { normalizeApiError } from "../utils/apiError";
import { formatPrice } from "../utils/formatPrice";
import { isExpressEligible } from "../utils/shipping";

const METHOD_LABELS = {
  standard: "ارسال عادی",
  express: "ارسال اکسپرس",
  pickup: "دریافت حضوری",
};

function methodLabel(id) {
  return METHOD_LABELS[id] || id;
}

function methodCostFor(method, subtotal) {
  if (!method) return 0;
  if (method.free_threshold != null && subtotal >= method.free_threshold) return 0;
  return method.cost ?? 0;
}

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

/** The only steps a checkout URL may name. Anything else (including a
 *  missing ?step) is replaced with the first one -- there is no
 *  single-page checkout that skips delivery/address/review. */
const STEP_IDS = ["delivery", "address", "review"];

function needsPlotAndUnit(address) {
  if (!address) return false;
  return !String(address.building_number || "").trim() || !String(address.unit || "").trim();
}

export default function CheckoutPage() {
  usePageMeta({ title: "تکمیل خرید", path: "/checkout/", noindex: true });
  const [searchParams, setSearchParams] = useSearchParams();

  const { cart, fetchCart } = useCartStore();
  const siteSettings = useSiteSettings();
  const isMobile = useMediaQuery("(max-width: 767px)");

  // Step in URL: delivery | address | review. The step IS the page: an
  // unknown or missing value is redirected to «delivery» below, so the
  // order can only ever be placed from the review step.
  const stepParam = searchParams.get("step");
  const hasValidStep = STEP_IDS.includes(stepParam);
  const currentStep = hasValidStep ? stepParam : "delivery";

  // Delivery methods state
  const [shippingData, setShippingData] = useState(null);
  const [shippingStatus, setShippingStatus] = useState("loading"); // loading | ready | error
  const [selectedMethod, setSelectedMethod] = useState(() => {
    try {
      return sessionStorage.getItem("cg_checkout_method") || null;
    } catch {
      return null;
    }
  });

  // Addresses state
  const [addresses, setAddresses] = useState([]);
  const [addressesStatus, setAddressesStatus] = useState("loading");
  const [addressLoadError, setAddressLoadError] = useState(null);
  const [addressMode, setAddressMode] = useState(() => {
    try {
      return sessionStorage.getItem("cg_checkout_addr_mode") || "saved";
    } catch {
      return "saved";
    }
  });
  const [selectedAddressId, setSelectedAddressId] = useState(() => {
    try {
      const stored = sessionStorage.getItem("cg_checkout_addr_id");
      return stored ? Number(stored) : null;
    } catch {
      return null;
    }
  });
  const [showAddressForm, setShowAddressForm] = useState(false);
  const [completingAddress, setCompletingAddress] = useState(null);
  const [inlineAddress, setInlineAddress] = useState({});
  const [addressErrors, setAddressErrors] = useState({});

  // Pickup contact state
  const [pickupContact, setPickupContact] = useState(() => {
    try {
      const stored = sessionStorage.getItem("cg_checkout_pickup");
      return stored ? JSON.parse(stored) : {};
    } catch {
      return {};
    }
  });
  const [pickupErrors, setPickupErrors] = useState({});

  // Coupon state
  const [couponCode, setCouponCode] = useState("");
  const [couponPreview, setCouponPreview] = useState(null);
  const [couponBusy, setCouponBusy] = useState(false);
  const [couponError, setCouponError] = useState(null);

  // Submission & payment state
  const [placing, setPlacing] = useState(false);
  const [stepError, setStepError] = useState(null);
  const [checkoutError, setCheckoutError] = useState(null);
  const [placedOrder, setPlacedOrder] = useState(null);
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState(null);

  const submittingRef = useRef(false);
  const forcedInlineRef = useRef(false);
  const addressesRef = useRef(addresses);
  addressesRef.current = addresses;

  // Track checkout_started once on entering step 2 (delivery)
  const trackedCheckoutStarted = useRef(false);
  useEffect(() => {
    if (currentStep === "delivery" && !trackedCheckoutStarted.current) {
      trackedCheckoutStarted.current = true;
      trackEvent("checkout_started");
    }
  }, [currentStep]);

  // Sync to sessionStorage
  useEffect(() => {
    try {
      if (selectedMethod) sessionStorage.setItem("cg_checkout_method", selectedMethod);
      if (selectedAddressId) sessionStorage.setItem("cg_checkout_addr_id", String(selectedAddressId));
      sessionStorage.setItem("cg_checkout_addr_mode", addressMode);
      if (pickupContact.recipient_name || pickupContact.phone) {
        sessionStorage.setItem("cg_checkout_pickup", JSON.stringify(pickupContact));
      }
    } catch {
      // ignore storage errors
    }
  }, [selectedMethod, selectedAddressId, addressMode, pickupContact]);

  // Load addresses
  const loadAddresses = useCallback((preferredId = null) => {
    setAddressesStatus("loading");
    setAddressLoadError(null);
    return authApi
      .listAddresses()
      .then((data) => {
        const list = Array.isArray(data) ? data : [];
        setAddresses(list);
        setAddressesStatus("ready");
        if (list.length === 0) {
          setSelectedAddressId(null);
          setAddressMode("inline");
          return;
        }
        const preferred =
          list.find((address) => address.id === preferredId) ||
          list.find((address) => address.id === selectedAddressId) ||
          list.find((address) => address.is_default) ||
          list[0];
        setSelectedAddressId(preferred ? preferred.id : null);
        if (forcedInlineRef.current) {
          forcedInlineRef.current = false;
          setAddressMode("saved");
        }
      })
      .catch((err) => {
        setAddressesStatus("error");
        setAddressLoadError(errorMessage(normalizeApiError(err)));
        if (addressesRef.current.length === 0) {
          forcedInlineRef.current = true;
          setAddressMode("inline");
        }
      });
  }, [selectedAddressId]);

  useEffect(() => {
    fetchCart();
    loadAddresses();
    fetchShippingMethods()
      .then((data) => {
        const methods = Array.isArray(data?.methods) ? data.methods : [];
        setShippingData({ ...data, methods });
        setSelectedMethod((prev) => {
          if (prev && methods.some((m) => m.id === prev)) return prev;
          const preferred = methods.find((m) => m.id === data?.default) || methods[0] || null;
          return preferred ? preferred.id : null;
        });
        setShippingStatus("ready");
      })
      .catch(() => setShippingStatus("error"));
  }, [fetchCart, loadAddresses]);

  const methods = shippingData?.methods || [];
  const currentMethod = methods.find((m) => m.id === selectedMethod) || null;
  const isPickup = currentMethod?.requires_address === false;

  const selectedAddress = addresses.find((a) => a.id === selectedAddressId) || null;
  const destination = addressMode === "saved" ? selectedAddress : inlineAddress;
  const isExpress = selectedMethod === "express";
  const destinationIsTehran = isExpressEligible(destination?.province, destination?.city);

  // Address validation for Step 3
  const checkDeliveryInfoValid = () => {
    if (isPickup) {
      return Boolean(
        String(pickupContact.recipient_name || "").trim() &&
        isValidIranianPhone(pickupContact.phone)
      );
    }
    if (addressMode === "saved") {
      if (!selectedAddressId || !selectedAddress) return false;
      if (isExpress && !isExpressEligible(selectedAddress.province, selectedAddress.city)) return false;
      return true;
    }
    const errors = validateAddressPayload(inlineAddress);
    if (Object.keys(errors).length > 0) return false;
    if (isExpress && !isExpressEligible(inlineAddress.province, inlineAddress.city)) return false;
    return true;
  };

  // A checkout URL without a valid step (the old /checkout/ link from the
  // cart, a typo, a stale bookmark) is REPLACED with the first step. There
  // is deliberately no legacy single-page mode: without this the cart's
  // «ادامه و ثبت سفارش» could open a form that skips review and coupon.
  useEffect(() => {
    if (hasValidStep) return;
    setSearchParams({ step: "delivery" }, { replace: true });
  }, [hasValidStep, setSearchParams]);

  // URL guards: later steps cannot be opened before earlier ones are done
  useEffect(() => {
    if (shippingStatus !== "ready" || (addressesStatus !== "ready" && !isPickup)) return;

    if (currentStep === "address") {
      if (!selectedMethod) {
        setSearchParams({ step: "delivery" }, { replace: true });
      }
    } else if (currentStep === "review") {
      if (!selectedMethod) {
        setSearchParams({ step: "delivery" }, { replace: true });
      } else if (!checkDeliveryInfoValid()) {
        setSearchParams({ step: "address" }, { replace: true });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStep, selectedMethod, shippingStatus, addressesStatus, isPickup]);

  const setStep = (step) => {
    setStepError(null);
    setSearchParams({ step });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Step 2 -> 3 transition
  const handleProceedFromDelivery = () => {
    setStepError(null);
    if (!selectedMethod) {
      setStepError("لطفاً یک روش تحویل انتخاب کنید.");
      return;
    }
    setStep("address");
  };

  // Step 3 -> 4 transition
  const handleProceedFromAddress = () => {
    setStepError(null);
    setPickupErrors({});
    setAddressErrors({});

    if (isPickup) {
      const name = String(pickupContact.recipient_name || "").trim();
      const phone = String(pickupContact.phone || "").trim();
      const errors = {};
      if (!name) errors.recipient_name = "نام تحویل‌گیرنده را وارد کنید.";
      if (!phone) {
        errors.phone = "شماره تماس را وارد کنید.";
      } else if (!isValidIranianPhone(phone)) {
        errors.phone = "فقط شمارهٔ موبایل (مثل ۰۹۱۲۳۴۵۶۷۸۹) قابل قبول است.";
      }
      if (Object.keys(errors).length > 0) {
        setPickupErrors(errors);
        setStepError("اطلاعات تحویل‌گیرنده کامل نیست.");
        return;
      }
      setStep("review");
      return;
    }

    if (addressMode === "saved") {
      if (!selectedAddressId || !selectedAddress) {
        setStepError("یک آدرس ذخیره‌شده انتخاب کنید یا آدرس جدید وارد کنید.");
        return;
      }
      if (isExpress && !isExpressEligible(selectedAddress.province, selectedAddress.city)) {
        setStepError("ارسال اکسپرس فقط برای شهر تهران در دسترس است. آدرس تهران انتخاب کنید یا روش ارسال را به عادی تغییر دهید.");
        return;
      }
      setStep("review");
      return;
    }

    // Inline address
    const localErrors = validateAddressPayload(inlineAddress);
    if (Object.keys(localErrors).length > 0) {
      setAddressErrors(localErrors);
      setStepError("آدرس ارسال کامل نیست؛ لطفاً موارد مشخص‌شده را تکمیل کنید.");
      const firstKey = ADDRESS_FIELD_ORDER.find((k) => localErrors[k]);
      if (firstKey) {
        document.getElementById(`addr-${firstKey}`)?.focus?.();
      }
      return;
    }
    if (isExpress && !isExpressEligible(inlineAddress.province, inlineAddress.city)) {
      setStepError("ارسال اکسپرس فقط برای شهر تهران در دسترس است. آدرس تهران انتخاب کنید یا روش ارسال را به عادی تغییر دهید.");
      return;
    }
    setStep("review");
  };

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

  // Step 4 final submission & payment redirect
  const placeOrder = async () => {
    if (submittingRef.current) return;
    setCheckoutError(null);
    setPayError(null);

    if (couponCode.trim() && !couponPreview && !couponError) {
      setCheckoutError(new Error("کد تخفیف را وارد کرده‌اید اما اعمال نشده است؛ دکمهٔ «اعمال» را بزنید یا کد را پاک کنید."));
      return;
    }

    submittingRef.current = true;
    setPlacing(true);
    try {
      const payload = isPickup
        ? {
            recipient_name: pickupContact.recipient_name.trim(),
            phone: normalizePhone(pickupContact.phone),
            shipping_method: "pickup",
          }
        : addressMode === "saved"
          ? { address_id: selectedAddressId, shipping_method: selectedMethod }
          : { ...inlineAddress, shipping_method: selectedMethod };

      if (couponPreview?.code) payload.coupon_code = couponPreview.code;

      const order = await checkout(payload);
      setPlacedOrder(order);
      fetchCart();

      // Initiate payment gateway redirect immediately
      setPaying(true);
      try {
        const paymentResult = await initiatePayment(order.id);
        if (paymentResult?.redirect_url) {
          window.location.href = paymentResult.redirect_url;
          return;
        }
      } catch (payErr) {
        setPayError(errorMessage(normalizeApiError(payErr)));
      } finally {
        setPaying(false);
      }
    } catch (err) {
      const normalized = normalizeApiError(err);
      setCheckoutError(normalized);
    } finally {
      submittingRef.current = false;
      setPlacing(false);
    }
  };

  const startPayment = async () => {
    if (!placedOrder) return;
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

  // Loading and empty states
  if (cart && cart.items.length === 0 && !placedOrder) {
    return (
      <div className="empty-state">
        <p className="empty-state__title">سبد خرید شما خالی است.</p>
        <Link className="btn btn--primary" to="/shop/">
          مشاهده فروشگاه
        </Link>
      </div>
    );
  }

  if (!cart && !placedOrder) return <Spinner label="در حال آماده‌سازی خرید…" />;

  // Placed order screen (if payment redirect didn't leave immediately)
  if (placedOrder) {
    return (
      <div className="checkout-done">
        <div className="checkout-done__icon" aria-hidden="true">
          <Icon name="check" size={32} />
        </div>
        <h1>سفارش شما ثبت شد</h1>
        <p className="checkout-done__number">
          شماره سفارش: <strong><bdi dir="ltr">{faDigits(placedOrder.order_number)}</bdi></strong>
        </p>

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
          {placedOrder.gift_wrap_fee > 0 ? (
            <div>
              <dt>بسته‌بندی هدیه</dt>
              <dd>{formatPrice(placedOrder.gift_wrap_fee)} تومان</dd>
            </div>
          ) : null}
          <div className="checkout-done__grand"><dt>مبلغ قابل پرداخت</dt><dd>{formatPrice(placedOrder.total)} تومان</dd></div>
        </dl>

        {placedOrder.estimated_delivery_min && placedOrder.estimated_delivery_max ? (
          <p className="checkout-done__delivery">
            تحویل تخمینی: {deliveryRange(placedOrder.estimated_delivery_min, placedOrder.estimated_delivery_max)}
          </p>
        ) : null}
        <button type="button" className="btn btn--primary" onClick={startPayment} disabled={paying}>
          {paying ? "در حال اتصال به درگاه…" : "پرداخت آنلاین"}
        </button>
        <p className="checkout-done__later">
          می‌توانید بعداً از بخش <Link to="/account/orders/">سفارش‌ها</Link> پرداخت را انجام دهید.
        </p>
        {payError ? <Alert>{payError}</Alert> : null}
      </div>
    );
  }

  // Invoice calculations
  const subtotal = cart.subtotal || 0;
  const previewedShippingCost = currentMethod ? methodCostFor(currentMethod, subtotal) : 0;
  const discountAmount = couponPreview?.discount_amount || 0;
  const payableTotal = Math.max(0, subtotal + previewedShippingCost - discountAmount);

  // Main action handler & label per step. The order is placed ONLY from the
  // review step -- delivery and address just move the flow forward.
  let stepActionHandler = handleProceedFromDelivery;
  let stepActionLabel = "ادامه: اطلاعات تحویل";

  if (currentStep === "address") {
    stepActionHandler = handleProceedFromAddress;
    stepActionLabel = "ادامه: بازبینی و پرداخت";
  } else if (currentStep === "review") {
    stepActionHandler = placeOrder;
    stepActionLabel = placing ? "در حال ثبت سفارش…" : "ثبت سفارش و پرداخت";
  }

  return (
    <div className="checkout">
      <h1 className="page-title">ثبت سفارش</h1>
      <CheckoutStepper currentStep={currentStep} />

      {stepError && <Alert>{stepError}</Alert>}

      <div className="checkout__body">
        <div className="checkout__grid">
          <main className="checkout__main">
            {/* ================= STEP 2: روش تحویل ================= */}
            {currentStep === "delivery" && (
              <section id="checkout-section-delivery" className="checkout__section">
                <h2>۲. انتخاب روش تحویل</h2>
                <p className="muted">لطفاً روش مورد نظر خود را برای دریافت سفارش انتخاب فرمایید:</p>

                {shippingStatus === "loading" && <Spinner label="در حال بارگیری روش‌های ارسال…" />}
                {shippingStatus === "error" && (
                  <Alert>خطا در بارگیری روش‌های ارسال. لطفاً دوباره تلاش کنید.</Alert>
                )}

                {shippingStatus === "ready" && (
                  <div className="shipping-cards-grid">
                    {methods.map((method) => {
                      const cost = methodCostFor(method, subtotal);
                      const isSelected = selectedMethod === method.id;
                      const isExpressMethod = method.id === "express";

                      return (
                        <div
                          key={method.id}
                          role="radio"
                          aria-checked={isSelected}
                          tabIndex={0}
                          className={`shipping-card ${isSelected ? "shipping-card--active" : ""}`}
                          onClick={() => setSelectedMethod(method.id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              setSelectedMethod(method.id);
                            }
                          }}
                        >
                          <div className="shipping-card__head">
                            <span className="shipping-card__icon" aria-hidden="true">
                              <Icon
                                name={
                                  method.requires_address === false
                                    ? "store"
                                    : isExpressMethod
                                      ? "bolt-fast"
                                      : "truck"
                                }
                                size={28}
                              />
                            </span>
                            <div className="shipping-card__title-group">
                              <h3 className="shipping-card__title">
                                {method.label || methodLabel(method.id)}
                              </h3>
                              {isExpressMethod && (
                                <span className="badge badge--gold">فقط شهر تهران</span>
                              )}
                            </div>
                            <span className="shipping-card__cost">
                              {cost === 0 ? "رایگان" : `${formatPrice(cost)} تومان`}
                            </span>
                          </div>

                          <div className="shipping-card__body">
                            {method.description ? (
                              /* The pickup method's description IS the owner's pickup
                                 hours (the API falls back to pickup_hours), so it gets
                                 the same bidi-safe rewrite as the pickup cards above. */
                              <p className="shipping-card__desc">{hoursRange(method.description)}</p>
                            ) : null}
                            <p className="shipping-card__time muted">
                              {method.requires_address === false
                                ? "تحویل در محل فروشگاه پس از هماهنگی"
                                : method.min_days != null
                                  ? deliveryDays(method.min_days, method.max_days)
                                  : ""}
                            </p>
                            {method.free_threshold && subtotal < method.free_threshold && cost > 0 ? (
                              <p className="shipping-card__free-hint muted">
                                ارسال برای خریدهای بالای {formatPrice(method.free_threshold)} تومان رایگان است.
                              </p>
                            ) : null}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                <div className="checkout__step-actions">
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={handleProceedFromDelivery}
                  >
                    ادامه: اطلاعات تحویل
                  </button>
                </div>
              </section>
            )}

            {/* ================= STEP 3: اطلاعات تحویل ================= */}
            {currentStep === "address" && (
              <section id="checkout-section-address" className="checkout__section">
                <h2>۳. اطلاعات تحویل</h2>

                {isPickup ? (
                  <div className="checkout__pickup-container">
                    <div className="checkout__pickup-info card">
                      <h3>اطلاعات دریافت حضوری</h3>
                      {siteSettings.pickup_address ? (
                        <p>
                          <strong>نشانی دریافت:</strong> {faDigits(siteSettings.pickup_address)}
                        </p>
                      ) : null}
                      {siteSettings.pickup_hours ? (
                        <p>
                          <strong>ساعات تحویل:</strong> {hoursRange(siteSettings.pickup_hours)}
                        </p>
                      ) : null}
                      <p className="muted">
                        برای دریافت سفارش در محل فروشگاه، تنها نام و شماره موبایل تحویل‌گیرنده لازم است.
                      </p>
                    </div>

                    <div className="checkout__pickup-form">
                      <label className="field">
                        <span>
                          نام تحویل‌گیرنده <span className="field__required">*</span>
                        </span>
                        <input
                          id="pickup-recipient_name"
                          type="text"
                          autoComplete="name"
                          value={pickupContact.recipient_name || ""}
                          onChange={(e) =>
                            setPickupContact((f) => ({ ...f, recipient_name: e.target.value }))
                          }
                          aria-invalid={Boolean(pickupErrors.recipient_name)}
                        />
                        {pickupErrors.recipient_name && (
                          <span className="field__error" role="alert">
                            {pickupErrors.recipient_name}
                          </span>
                        )}
                      </label>

                      <label className="field">
                        <span>
                          شماره تماس (موبایل) <span className="field__required">*</span>
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
                          aria-invalid={Boolean(pickupErrors.phone)}
                        />
                        {pickupErrors.phone && (
                          <span className="field__error" role="alert">
                            {pickupErrors.phone}
                          </span>
                        )}
                      </label>
                    </div>
                  </div>
                ) : (
                  <div className="checkout__address-container">
                    {isExpress && (
                      <p className="checkout__notice alert--warning">
                        شما ارسال اکسپرس را انتخاب کرده‌اید. ارسال اکسپرس فقط برای شهر تهران در دسترس است.
                      </p>
                    )}

                    <div className="checkout__mode-switch">
                      {addresses.length > 0 ? (
                        <>
                          <label>
                            <input
                              type="radio"
                              name="addressMode"
                              checked={addressMode === "saved"}
                              onChange={() => setAddressMode("saved")}
                            />
                            آدرس‌های ذخیره شده
                          </label>
                          <label>
                            <input
                              type="radio"
                              name="addressMode"
                              checked={addressMode === "inline"}
                              onChange={() => setAddressMode("inline")}
                            />
                            آدرس جدید (یک‌بار مصرف)
                          </label>
                        </>
                      ) : (
                        <p>هیچ آدرس ذخیره‌شده‌ای ندارید؛ آدرس خود را وارد کنید.</p>
                      )}
                    </div>

                    {addressesStatus === "error" && (
                      <div className="checkout__notice" role="status">
                        <p>
                          فهرست آدرس‌های ذخیره‌شده بارگیری نشد
                          {addressLoadError ? `: ${addressLoadError}` : "."} می‌توانید آدرس را دستی وارد کنید.
                        </p>
                        <button type="button" className="btn btn--outline btn--sm" onClick={loadAddresses}>
                          تلاش دوباره برای آدرس‌ها
                        </button>
                      </div>
                    )}

                    {addressMode === "saved" && addresses.length > 0 && (
                      <div className="address-list">
                        {addresses.map((address) => {
                          const isEligible = !isExpress || isExpressEligible(address.province, address.city);
                          const isSelected = selectedAddressId === address.id;

                          return (
                            <label
                              key={address.id}
                              className={`address-card ${!isEligible ? "address-card--disabled" : ""}`}
                            >
                              <input
                                type="radio"
                                name="address"
                                checked={isSelected && isEligible}
                                disabled={!isEligible}
                                onChange={() => {
                                  if (isEligible) setSelectedAddressId(address.id);
                                }}
                              />
                              <span>
                                <strong>{address.recipient_name}</strong> — {formatAddress(address)}
                                {address.is_default && <em className="address-card__default">پیش‌فرض</em>}
                                {!isEligible && (
                                  <span className="checkout__express-warning">
                                    ارسال اکسپرس فقط برای شهر تهران در دسترس است.
                                  </span>
                                )}
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    )}

                    {selectedAddress && isExpress && !destinationIsTehran && addressMode === "saved" && (
                      <div className="checkout__notice alert--warning" role="alert">
                        <p>
                          آدرس انتخابی مربوط به شهر تهران نیست و ارسال اکسپرس برای آن مقدور نمی‌باشد.
                        </p>
                        <button
                          type="button"
                          className="btn btn--outline btn--sm"
                          onClick={() => setSelectedMethod("standard")}
                        >
                          تغییر به ارسال عادی
                        </button>
                      </div>
                    )}

                    {selectedAddress && needsPlotAndUnit(selectedAddress) && addressMode === "saved" && (
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
                    )}

                    {completingAddress && (
                      <AddressForm
                        initial={completingAddress}
                        compact
                        onSaved={async (saved) => {
                          setCompletingAddress(null);
                          await loadAddresses(saved.id);
                        }}
                      />
                    )}

                    {addressMode === "inline" ? (
                      <div>
                        {isExpress && !destinationIsTehran && (inlineAddress.province || inlineAddress.city) && (
                          <div className="checkout__notice alert--warning" role="alert">
                            <p>ارسال اکسپرس فقط برای شهر تهران است. مایلید روش ارسال به «ارسال عادی» تغییر کند؟</p>
                            <button
                              type="button"
                              className="btn btn--outline btn--sm"
                              onClick={() => setSelectedMethod("standard")}
                            >
                              تغییر به ارسال عادی
                            </button>
                          </div>
                        )}
                        <AddressForm
                          value={inlineAddress}
                          onChange={(next) => {
                            setInlineAddress(next);
                            if (Object.keys(addressErrors).length) setAddressErrors({});
                          }}
                          fieldErrors={addressErrors}
                          compact
                        />
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="link"
                        onClick={() => setShowAddressForm((v) => !v)}
                      >
                        {showAddressForm ? "بستن فرم آدرس جدید" : "+ ذخیره آدرس جدید"}
                      </button>
                    )}

                    {showAddressForm && addressMode === "saved" && (
                      <AddressForm
                        onSaved={async (address) => {
                          setShowAddressForm(false);
                          await loadAddresses(address.id);
                        }}
                        compact
                      />
                    )}
                  </div>
                )}

                <div className="checkout__step-actions">
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={handleProceedFromAddress}
                  >
                    ادامه: بازبینی و پرداخت
                  </button>
                </div>
              </section>
            )}

            {/* ================= STEP 4: بازبینی و پرداخت ================= */}
            {currentStep === "review" && (
              <section id="checkout-section-review" className="checkout__section checkout__review">
                <h2>۴. بازبینی و پرداخت</h2>

                {/* اقلام سفارش */}
                <div className="checkout__review-block card">
                  <div className="checkout__review-block-head">
                    <h3>اقلام سبد خرید ({faDigits(cart.item_count)} کالا)</h3>
                    <Link to="/cart/" className="btn btn--link btn--sm">
                      تغییر سبد خرید
                    </Link>
                  </div>
                  <ul className="checkout__review-items">
                    {cart.items.map((item) => (
                      <li key={item.id} className="checkout__review-item">
                        <SmartImage
                          image={item.product?.primary_image || null}
                          alt={faDigits(item.product?.name || "")}
                          width={54}
                          height={54}
                        />
                        <div className="checkout__review-item-details">
                          <span className="checkout__review-item-name">{faDigits(item.product?.name)}</span>
                          {item.variant && (
                            <small className="muted">
                              {faDigits(item.variant.attribute_values?.map((av) => `${av.attribute}: ${av.value}`).join("، "))}
                            </small>
                          )}
                          <span className="checkout__review-item-qty">
                            تعداد: {faDigits(item.quantity)}
                          </span>
                        </div>
                        <span className="checkout__review-item-price">
                          {formatPrice(item.line_total)} تومان
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* روش تحویل */}
                <div className="checkout__review-block card">
                  <div className="checkout__review-block-head">
                    <h3>روش تحویل انتخاب‌شده</h3>
                    <button
                      type="button"
                      className="btn btn--link btn--sm"
                      onClick={() => setStep("delivery")}
                    >
                      تغییر
                    </button>
                  </div>
                  <div className="checkout__review-block-body">
                    <strong>{currentMethod?.label || methodLabel(currentMethod?.id)}</strong>
                    <p className="muted">
                      {currentMethod?.requires_address === false
                        ? "تحویل حضوری در محل فروشگاه پس از هماهنگی"
                        : currentMethod?.min_days != null
                          ? deliveryDays(currentMethod.min_days, currentMethod.max_days)
                          : ""}
                    </p>
                    <span className="checkout__review-cost">
                      هزینه ارسال: {previewedShippingCost === 0 ? "رایگان" : `${formatPrice(previewedShippingCost)} تومان`}
                    </span>
                  </div>
                </div>

                {/* اطلاعات تحویل یا آدرس */}
                <div className="checkout__review-block card">
                  <div className="checkout__review-block-head">
                    <h3>{isPickup ? "اطلاعات تحویل‌گیرنده" : "آدرس تحویل"}</h3>
                    <button
                      type="button"
                      className="btn btn--link btn--sm"
                      onClick={() => setStep("address")}
                    >
                      تغییر
                    </button>
                  </div>
                  <div className="checkout__review-block-body">
                    {isPickup ? (
                      <>
                        <p>
                          <strong>تحویل‌گیرنده:</strong> {pickupContact.recipient_name}
                        </p>
                        <p>
                          <strong>شماره تماس:</strong> {faDigits(pickupContact.phone)}
                        </p>
                        {siteSettings.pickup_address && (
                          <p>
                            <strong>نشانی دریافت:</strong> {faDigits(siteSettings.pickup_address)}
                          </p>
                        )}
                        {siteSettings.pickup_hours && (
                          <p>
                            <strong>ساعات دریافت:</strong> {hoursRange(siteSettings.pickup_hours)}
                          </p>
                        )}
                      </>
                    ) : (
                      <>
                        <p>
                          <strong>گیرنده:</strong> {destination?.recipient_name} —{" "}
                          {faDigits(destination?.phone)}
                        </p>
                        <p>
                          <strong>نشانی:</strong> {formatAddress(destination || {})}
                        </p>
                        {destination?.postal_code && (
                          <p>
                            <strong>کد پستی:</strong> {faDigits(destination.postal_code)}
                          </p>
                        )}
                      </>
                    )}
                  </div>
                </div>

                {/* کوپن تخفیف */}
                <div className="checkout__review-block card">
                  <h3>کد تخفیف</h3>
                  <div className="coupon-row">
                    <input
                      type="text"
                      dir="ltr"
                      value={couponCode}
                      id="checkout-coupon"
                      placeholder="کد تخفیف را وارد کنید"
                      onChange={(e) => {
                        setCouponCode(e.target.value);
                        setCouponError(null);
                        setCouponPreview(null);
                      }}
                    />
                    <button
                      type="button"
                      className="btn btn--outline"
                      onClick={applyCoupon}
                      disabled={couponBusy}
                    >
                      {couponBusy ? "…" : "اعمال"}
                    </button>
                  </div>
                  {couponError && <Alert>{couponError}</Alert>}
                  {couponPreview && (
                    <Alert kind="success">
                      کد «{couponPreview.code}» اعمال شد: {formatPrice(couponPreview.discount_amount)} تومان تخفیف.
                    </Alert>
                  )}
                </div>

                {checkoutError && <Alert>{errorMessage(checkoutError)}</Alert>}
              </section>
            )}
          </main>

          {/* ================= INVOICE SUMMARY (VISIBLE ON EVERY STEP) ================= */}
          <aside className="checkout__summary card">
            <h2>خلاصه سفارش</h2>
            <dl>
              <div>
                <dt>جمع کالاها ({faDigits(cart.item_count)})</dt>
                <dd>{formatPrice(subtotal)} تومان</dd>
              </div>
              <div>
                <dt>
                  هزینه ارسال
                  {currentMethod ? ` (${currentMethod.label || methodLabel(currentMethod.id)})` : ""}
                </dt>
                <dd>
                  {previewedShippingCost === 0 ? "رایگان" : `${formatPrice(previewedShippingCost)} تومان`}
                </dd>
              </div>
              {couponPreview && (
                <div>
                  <dt>تخفیف</dt>
                  <dd>− {formatPrice(couponPreview.discount_amount)} تومان</dd>
                </div>
              )}
              <div className="checkout__grand">
                <dt>مبلغ قابل پرداخت</dt>
                <dd>{formatPrice(payableTotal)} تومان</dd>
              </div>
            </dl>

            <button
              type="button"
              className="btn btn--primary btn--block checkout__desktop-action"
              disabled={placing}
              onClick={stepActionHandler}
            >
              {stepActionLabel}
            </button>
          </aside>
        </div>
      </div>

      {/* ================= MOBILE BOTTOM STICKY BAR ================= */}
      {isMobile ? (
        <div className="checkout__mobile-bar">
          <div className="checkout__mobile-bar-row">
            <span className="checkout__mobile-total">
              <small>مبلغ قابل پرداخت</small>
              <b>{formatPrice(payableTotal)} تومان</b>
            </span>
            <button
              type="button"
              className="btn btn--primary"
              disabled={placing}
              onClick={stepActionHandler}
            >
              {stepActionLabel}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
