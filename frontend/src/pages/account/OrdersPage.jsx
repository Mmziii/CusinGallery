import { useState } from "react";
import { Link } from "react-router-dom";

import { Alert, EmptyState, Spinner, errorMessage } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import { fetchOrders } from "../../services/orderApi";
import { formatPrice } from "../../utils/formatPrice";

export const ORDER_STATUS_LABELS = {
  pending: "در انتظار پرداخت",
  confirmed: "تأیید شده",
  processing: "در حال پردازش",
  shipped: "ارسال شده",
  delivered: "تحویل شده",
  cancelled: "لغو شده",
  returned: "مرجوع شده",
};

export const PAYMENT_STATUS_LABELS = {
  unpaid: "پرداخت نشده",
  pending: "در انتظار پرداخت",
  paid: "پرداخت شده",
  failed: "پرداخت ناموفق",
  refunded: "بازپرداخت شده",
};

function OrdersPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading, error } = useAsync(() => fetchOrders({ page }), [page]);

  if (isLoading) return <Spinner label="در حال دریافت سفارش‌ها…" />;
  if (error) return <Alert>{errorMessage(error)}</Alert>;
  if (!data?.results?.length) {
    return (
      <EmptyState title="هنوز سفارشی ثبت نکرده‌اید.">
        <Link className="btn btn--primary" to="/shop/">شروع خرید</Link>
      </EmptyState>
    );
  }

  const totalPages = Math.ceil(data.count / 20);

  return (
    <div className="orders-page">
      <h1>سفارش‌های من</h1>
      <div className="order-list">
        {data.results.map((order) => (
          <Link key={order.id} to={`/account/orders/${order.id}/`} className="order-row">
            <div>
              <strong>{order.order_number}</strong>
              <span className="muted">{new Date(order.created_at).toLocaleDateString("fa-IR")}</span>
            </div>
            <div className="order-row__meta">
              <span className={`tag tag--${order.payment_status}`}>
                {PAYMENT_STATUS_LABELS[order.payment_status] || order.payment_status}
              </span>
              <span className={`tag tag--status-${order.status}`}>
                {ORDER_STATUS_LABELS[order.status] || order.status}
              </span>
            </div>
            <div className="order-row__total">{formatPrice(order.total)} تومان</div>
          </Link>
        ))}
      </div>

      {totalPages > 1 ? (
        <nav className="pagination">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>قبلی</button>
          <span>صفحه {page} از {totalPages}</span>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>بعدی</button>
        </nav>
      ) : null}
    </div>
  );
}

export default OrdersPage;
