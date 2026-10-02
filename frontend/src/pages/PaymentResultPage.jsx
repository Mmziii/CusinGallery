import { Link, useParams, useSearchParams } from "react-router-dom";

import { Alert, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { fetchPayment } from "../services/paymentsApi";
import useAuthStore from "../store/useAuthStore";
import { formatPrice } from "../utils/formatPrice";

/**
 * Landing page after the gateway redirect. If a payment id is present,
 * the authoritative status comes from GET /payments/{id}/ (never from the
 * query string -- that only seeds the initial icon while the request is
 * in flight). An invalid callback (unknown authority) arrives with no id
 * and ?status=failed.
 */
function PaymentResultPage() {
  const { paymentId } = useParams();
  const [searchParams] = useSearchParams();
  const { isAuthenticated } = useAuthStore();
  const hintedStatus = searchParams.get("status");

  const { data: payment, isLoading, error } = useAsync(
    () => (paymentId ? fetchPayment(paymentId) : Promise.resolve(null)),
    [paymentId]
  );

  if (paymentId && isLoading) return <Spinner label="در حال بررسی نتیجه پرداخت…" />;

  const status = payment?.status || hintedStatus;

  if (!paymentId || !payment) {
    return (
      <div className="payment-result payment-result--failed">
        <h1>پرداخت ناموفق</h1>
        <p>
          {status === "cancelled"
            ? "شما از درگاه پرداخت بازگشتید و تراکنشی انجام نشد."
            : "پرداخت تأیید نشد یا تراکنش معتبر نبود."}
        </p>
        {isAuthenticated ? (
          <Link className="btn btn--primary" to="/account/orders/">
            مشاهده سفارش‌ها و تلاش دوباره
          </Link>
        ) : null}
      </div>
    );
  }

  const isSuccess = payment.status === "success";
  const isCancelled = payment.status === "cancelled";

  return (
    <div className={`payment-result ${isSuccess ? "payment-result--success" : "payment-result--failed"}`}>
      <div className="payment-result__icon" aria-hidden="true">{isSuccess ? "✓" : isCancelled ? "↩" : "✕"}</div>
      <h1>{isSuccess ? "پرداخت با موفقیت انجام شد" : isCancelled ? "پرداخت لغو شد" : "پرداخت ناموفق بود"}</h1>

      <dl className="payment-result__details">
        <div><dt>شماره سفارش</dt><dd>{payment.order_number}</dd></div>
        <div><dt>مبلغ</dt><dd>{formatPrice(payment.amount)} تومان</dd></div>
        <div><dt>وضعیت</dt><dd>{statusLabel(payment.status)}</dd></div>
        {payment.gateway_ref_id ? (
          <div><dt>شماره مرجع درگاه</dt><dd dir="ltr">{payment.gateway_ref_id}</dd></div>
        ) : null}
        {payment.paid_at ? (
          <div><dt>زمان پرداخت</dt><dd>{new Date(payment.paid_at).toLocaleString("fa-IR")}</dd></div>
        ) : null}
        {payment.failure_reason && !isSuccess ? (
          <div><dt>دلیل</dt><dd>{failureLabel(payment.failure_reason)}</dd></div>
        ) : null}
      </dl>

      {error ? <Alert>دریافت جزئیات پرداخت ناموفق بود.</Alert> : null}

      <div className="payment-result__actions">
        <Link className="btn btn--primary" to={`/account/orders/`}>مشاهده سفارش‌ها</Link>
        <Link className="btn btn--outline" to="/shop/">بازگشت به فروشگاه</Link>
      </div>
    </div>
  );
}

function statusLabel(status) {
  return {
    success: "موفق",
    failed: "ناموفق",
    cancelled: "لغو شده",
    pending: "در انتظار",
  }[status] || status;
}

function failureLabel(reason) {
  if (reason === "cancelled_by_customer") return "انصراف مشتری در درگاه پرداخت";
  return reason;
}

export default PaymentResultPage;
