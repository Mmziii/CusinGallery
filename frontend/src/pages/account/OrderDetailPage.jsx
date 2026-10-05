import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import SmartImage from "../../components/SmartImage";
import { Alert, ErrorState, Spinner, errorMessage } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import { fetchOrder } from "../../services/orderApi";
import { initiatePayment } from "../../services/paymentsApi";
import { normalizeApiError } from "../../utils/apiError";
import { formatPrice } from "../../utils/formatPrice";
import { ORDER_STATUS_LABELS, PAYMENT_STATUS_LABELS } from "./OrdersPage";

function OrderDetailPage() {
  const { orderId } = useParams();
  const { data: order, isLoading, error, refetch } = useAsync(() => fetchOrder(orderId), [orderId]);

  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState(null);

  if (isLoading) return <Spinner label="در حال دریافت سفارش…" />;
  if (error) return <ErrorState message={errorMessage(error)} onRetry={refetch} />;
  if (!order) return null;

  // unpaid/failed are obviously retryable; "pending" means a previous
  // attempt was started but never finished -- initiating again is safe
  // (each attempt is its own Payment row).
  const payable = ["unpaid", "failed", "pending"].includes(order.payment_status);

  const pay = async () => {
    setPayError(null);
    setPaying(true);
    try {
      const result = await initiatePayment(order.id);
      window.location.href = result.redirect_url;
    } catch (err) {
      setPayError(errorMessage(normalizeApiError(err)));
      setPaying(false);
    }
  };

  return (
    <div className="order-detail">
      <div className="page-head">
        <h1>سفارش {order.order_number}</h1>
        <Link to="/account/orders/" className="link">بازگشت به سفارش‌ها</Link>
      </div>

      <div className="order-detail__meta card">
        <dl>
          <div><dt>تاریخ ثبت</dt><dd>{new Date(order.created_at).toLocaleString("fa-IR")}</dd></div>
          <div>
            <dt>وضعیت سفارش</dt>
            <dd>{ORDER_STATUS_LABELS[order.status] || order.status}</dd>
          </div>
          <div>
            <dt>وضعیت پرداخت</dt>
            <dd>{PAYMENT_STATUS_LABELS[order.payment_status] || order.payment_status}</dd>
          </div>
          <div>
            <dt>روش ارسال</dt>
            <dd>
              {order.shipping_method === "express"
                ? "ارسال اکسپرس"
                : order.shipping_method === "pickup"
                  ? "دریافت حضوری"
                  : "ارسال عادی"}
            </dd>
          </div>
          {order.gift_wrap ? (
            <div>
              <dt>بسته‌بندی هدیه</dt>
              <dd>
                بله{order.gift_message ? ` — پیام: ${order.gift_message}` : ""}
              </dd>
            </div>
          ) : null}
          {order.payment_status === "paid" ? (
            <div>
              <dt>فاکتور</dt>
              <dd>
                <a href={`/api/v1/orders/${order.id}/invoice/`} target="_blank" rel="noopener noreferrer">
                  مشاهده و چاپ فاکتور
                </a>
              </dd>
            </div>
          ) : null}
          {order.estimated_delivery_min && order.estimated_delivery_max ? (
            <div>
              <dt>تحویل تخمینی</dt>
              <dd>
                {new Date(order.estimated_delivery_min).toLocaleDateString("fa-IR")} تا{" "}
                {new Date(order.estimated_delivery_max).toLocaleDateString("fa-IR")}
              </dd>
            </div>
          ) : null}
        </dl>

        {payable ? (
          <div className="order-detail__pay">
            <button type="button" className="btn btn--primary" onClick={pay} disabled={paying}>
              {paying ? "در حال اتصال به درگاه…" : `پرداخت ${formatPrice(order.total)} تومان`}
            </button>
            {payError ? <Alert>{payError}</Alert> : null}
          </div>
        ) : null}
      </div>

      <div className="order-detail__items card">
        <h2>اقلام سفارش</h2>
        <table>
          <thead>
            <tr><th>کالا</th><th>فی</th><th>تعداد</th><th>جمع</th></tr>
          </thead>
          <tbody>
            {order.items.map((item) => (
              <tr key={item.id}>
                <td>
                  <span className="order-detail__itemline">
                    <SmartImage image={item.product_image || null} alt="" />
                    <span>
                      {item.product_slug ? (
                        <Link to={`/products/${item.product_slug}/`}>{item.product_name}</Link>
                      ) : (
                        item.product_name
                      )}
                      <div className="muted" dir="ltr">{item.sku}</div>
                    </span>
                  </span>
                </td>
                <td>{formatPrice(item.unit_price)}</td>
                <td>{item.quantity}</td>
                <td>{formatPrice(item.total_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="order-detail__totals card">
        <dl>
          <div><dt>جمع کالاها</dt><dd>{formatPrice(order.subtotal)} تومان</dd></div>
          {order.discount_amount > 0 ? (
            <div>
              <dt>تخفیف{order.coupon_code ? ` (${order.coupon_code})` : ""}</dt>
              <dd>− {formatPrice(order.discount_amount)} تومان</dd>
            </div>
          ) : null}
          <div>
            <dt>هزینه ارسال</dt>
            <dd>{order.shipping_cost === 0 ? "رایگان" : `${formatPrice(order.shipping_cost)} تومان`}</dd>
          </div>
          <div className="order-detail__grand"><dt>مبلغ کل</dt><dd>{formatPrice(order.total)} تومان</dd></div>
        </dl>
      </div>

      <div className="order-detail__address card">
        <h2>آدرس ارسال</h2>
        <p>
          {order.shipping_recipient_name} — {order.shipping_phone}
        </p>
        <p>
          {order.shipping_province}، {order.shipping_city}، {order.shipping_address}
          {order.shipping_unit ? `، واحد ${order.shipping_unit}` : ""}
          {order.shipping_building_number ? `، پلاک ${order.shipping_building_number}` : ""}
        </p>
        <p className="muted">کد پستی: {order.shipping_postal_code}</p>
      </div>
    </div>
  );
}

export default OrderDetailPage;
