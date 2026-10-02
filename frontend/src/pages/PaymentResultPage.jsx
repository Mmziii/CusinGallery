import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { Alert, Spinner, errorMessage } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { fetchPayment, initiatePayment } from "../services/paymentsApi";
import useAuthStore from "../store/useAuthStore";
import { normalizeApiError } from "../utils/apiError";
import { formatPrice } from "../utils/formatPrice";

/**
 * Landing page after the gateway redirect. If a payment id is present,
 * the authoritative status comes from GET /payments/{id}/ (never from the
 * query string -- that only seeds the initial view while the request is
 * in flight). An invalid callback (unknown authority) arrives with no id
 * and ?status=failed.
 *
 * All four outcomes are handled with their own Persian copy and a clear
 * next action each (Phase C):
 *   success   -> view the order / back to the shop
 *   failed    -> retry payment (a NEW attempt), view order, back to cart
 *   cancelled -> same as failed: nothing was charged, paying again is safe
 *   pending   -> the backend could not reach the gateway to finalize the
 *                result yet (or the attempt is still in flight): re-check,
 *                view the order -- deliberately NO retry button here, so
 *                a customer never starts a second attempt while the first
 *                one's money state is still unknown.
 */
function PaymentResultPage() {
  const { paymentId } = useParams();
  const [searchParams] = useSearchParams();
  const { isAuthenticated } = useAuthStore();
  const hintedStatus = searchParams.get("status");

  const { data: payment, isLoading, error, refetch } = useAsync(
    () => (paymentId ? fetchPayment(paymentId) : Promise.resolve(null)),
    [paymentId]
  );

  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState(null);

  if (paymentId && isLoading) return <Spinner label="در حال بررسی نتیجه پرداخت…" />;

  const retryPayment = async () => {
    if (!payment) return;
    setRetryError(null);
    setRetrying(true);
    try {
      const result = await initiatePayment(payment.order_id);
      window.location.href = result.redirect_url;
    } catch (err) {
      setRetryError(errorMessage(normalizeApiError(err)));
      setRetrying(false);
    }
  };

  // No payment id (invalid/unknown callback) or the fetch failed: fall
  // back to the query-string hint, which is only ever used for copy --
  // nothing is trusted from it.
  if (!paymentId || !payment) {
    const cancelledHint = (hintedStatus || "failed") === "cancelled";
    return (
      <div className={`payment-result payment-result--${cancelledHint ? "cancelled" : "failed"}`}>
        <div className="payment-result__icon" aria-hidden="true">{cancelledHint ? "↩" : "✕"}</div>
        <h1>{cancelledHint ? "پرداخت لغو شد" : "پرداخت ناموفق"}</h1>
        <p>
          {cancelledHint
            ? "شما از درگاه پرداخت بازگشتید و تراکنشی انجام نشد؛ مبلغی از حساب شما کسر نشده است."
            : "پرداخت تأیید نشد یا تراکنش معتبر نبود. در صورت کسر مبلغ، معمولاً طی ۷۲ ساعت توسط بانک بازگردانده می‌شود."}
        </p>
        <div className="payment-result__actions">
          <Link className="btn btn--primary" to="/cart/">بازگشت به سبد خرید</Link>
          {isAuthenticated ? (
            <Link className="btn btn--outline" to="/account/orders/">مشاهده سفارش‌ها و تلاش دوباره</Link>
          ) : null}
        </div>
      </div>
    );
  }

  const status = payment.status;
  const isSuccess = status === "success";
  const isCancelled = status === "cancelled";
  const isPending = status === "pending";
  const variant = isSuccess ? "success" : isCancelled ? "cancelled" : isPending ? "pending" : "failed";
  // Retry starts a NEW payment attempt (its own Payment row) -- safe after
  // a definitive failed/cancelled outcome, never offered while pending.
  const canRetry = (isCancelled || variant === "failed") && isAuthenticated;

  return (
    <div className={`payment-result payment-result--${variant}`}>
      <div className="payment-result__icon" aria-hidden="true">
        {isSuccess ? "✓" : isCancelled ? "↩" : isPending ? "…" : "✕"}
      </div>
      <h1>
        {isSuccess
          ? "پرداخت با موفقیت انجام شد"
          : isCancelled
            ? "پرداخت لغو شد"
            : isPending
              ? "بررسی نتیجه پرداخت در جریان است"
              : "پرداخت ناموفق بود"}
      </h1>
      <p className="payment-result__lead">
        {isCancelled
          ? "تراکنشی انجام نشد و مبلغی از حساب شما کسر نشده است. می‌توانید دوباره پرداخت کنید."
          : isPending
            ? "نتیجهٔ تراکنش هنوز قطعی نشده است. کمی صبر کنید و سپس وضعیت را دوباره بررسی کنید؛ سفارش تا روشن شدن نتیجه در فهرست سفارش‌های شما قابل پیگیری است."
            : null}
      </p>

      <dl className="payment-result__details">
        <div><dt>شماره سفارش</dt><dd>{payment.order_number}</dd></div>
        <div><dt>مبلغ</dt><dd>{formatPrice(payment.amount)} تومان</dd></div>
        <div><dt>وضعیت</dt><dd>{statusLabel(status)}</dd></div>
        {payment.gateway_ref_id ? (
          <div><dt>شماره مرجع درگاه</dt><dd dir="ltr">{payment.gateway_ref_id}</dd></div>
        ) : null}
        {payment.paid_at ? (
          <div><dt>زمان پرداخت</dt><dd>{new Date(payment.paid_at).toLocaleString("fa-IR")}</dd></div>
        ) : null}
        {payment.estimated_delivery_min && payment.estimated_delivery_max ? (
          <div>
            <dt>تحویل تخمینی</dt>
            <dd>
              {new Date(payment.estimated_delivery_min).toLocaleDateString("fa-IR")} تا{" "}
              {new Date(payment.estimated_delivery_max).toLocaleDateString("fa-IR")}
              {" "}({payment.shipping_method === "express" ? "ارسال اکسپرس" : "ارسال استاندارد"})
            </dd>
          </div>
        ) : null}
        {payment.failure_reason && !isSuccess ? (
          <div><dt>دلیل</dt><dd>{failureLabel(payment.failure_reason)}</dd></div>
        ) : null}
      </dl>

      {isPending ? (
        <Alert kind="info">
          اگر مبلغی از حساب شما کسر شده و تراکنش موفق نبوده است، معمولاً طی ۷۲ ساعت
          به‌صورت خودکار توسط بانک بازگردانده می‌شود.
        </Alert>
      ) : null}
      {error ? <Alert>دریافت جزئیات پرداخت ناموفق بود.</Alert> : null}
      {retryError ? <Alert>{retryError}</Alert> : null}

      <div className="payment-result__actions">
        {canRetry ? (
          <button type="button" className="btn btn--primary" onClick={retryPayment} disabled={retrying}>
            {retrying ? "در حال اتصال به درگاه…" : "تلاش دوباره برای پرداخت"}
          </button>
        ) : null}
        {isPending ? (
          <button type="button" className="btn btn--primary" onClick={refetch}>بررسی مجدد نتیجه</button>
        ) : null}
        <Link
          className={`btn ${canRetry || isPending ? "btn--outline" : "btn--primary"}`}
          to={`/account/orders/${payment.order_id}/`}
        >
          مشاهده سفارش
        </Link>
        {isSuccess ? (
          <Link className="btn btn--outline" to="/shop/">بازگشت به فروشگاه</Link>
        ) : (
          <Link className="btn btn--outline" to="/cart/">بازگشت به سبد خرید</Link>
        )}
      </div>
    </div>
  );
}

function statusLabel(status) {
  return {
    success: "موفق",
    failed: "ناموفق",
    cancelled: "لغو شده",
    pending: "در انتظار تعیین نتیجه",
  }[status] || status;
}

function failureLabel(reason) {
  if (reason === "cancelled_by_customer") return "انصراف مشتری در درگاه پرداخت";
  if (reason === "cancelled_or_failed_at_gateway") return "تراکنش در درگاه پرداخت ناموفق بود یا لغو شد";
  return reason;
}

export default PaymentResultPage;
