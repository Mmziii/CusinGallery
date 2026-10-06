import { usePageMeta } from "../hooks/usePageMeta";
import { useState } from "react";
import { Link } from "react-router-dom";

import PriceTag from "../components/PriceTag";
import SmartImage from "../components/SmartImage";
import { EmptyState, ErrorState, Spinner, errorMessage } from "../components/ui";
import { useWishlist } from "../hooks/useWishlist";
import useCartStore from "../store/useCartStore";
import { toast } from "../utils/toast";

function WishlistPage() {
  usePageMeta({ title: "علاقه‌مندی‌ها", path: "/wishlist/", noindex: true });
  const { items, isLoading, error, removeItem, refetch } = useWishlist();
  const addToCart = useCartStore((s) => s.addItem);
  // Part S2 item 6: per-row busy flags (no double submit) + feedback.
  const [busyId, setBusyId] = useState(null);

  const handleRemove = async (id) => {
    if (!window.confirm("این کالا از علاقه‌مندی‌ها حذف شود؟")) return;
    setBusyId(id);
    await removeItem(id);
    setBusyId(null);
  };

  const handleAddToCart = async (productId) => {
    setBusyId(`cart-${productId}`);
    const result = await addToCart(productId, null, 1);
    setBusyId(null);
    if (result?.success) {
      toast("به سبد خرید اضافه شد", "success", { label: "مشاهده سبد", to: "/cart/" });
    } else if (result?.error) {
      toast(errorMessage(result.error) || "افزودن به سبد انجام نشد.", "error");
    }
  };

  if (isLoading) return <Spinner label="در حال دریافت علاقه‌مندی‌ها…" />;
  if (error) return <ErrorState message={errorMessage(error)} onRetry={refetch} />;

  if (!items.length) {
    return (
      <EmptyState title="لیست علاقه‌مندی شما خالی است.">
        <Link className="btn btn--primary" to="/shop/">مشاهده فروشگاه</Link>
      </EmptyState>
    );
  }

  return (
    <div className="wishlist-page">
      <h1>علاقه‌مندی‌ها</h1>
      <div className="wishlist-grid">
        {items.map((item) => {
          const product = item.product;
          // is_available = still published at all; stock_status = current
          // purchasability. Both come from the server.
          const unavailable = !item.is_available || product.stock_status === "out_of_stock";
          return (
            <div key={item.id} className="product-card">
              <Link to={`/products/${product.slug}/`} className="product-card__media">
                <SmartImage image={product.primary_image || null} alt={product.name} />
              </Link>
              <div className="product-card__body">
                <Link to={`/products/${product.slug}/`} className="product-card__name">{product.name}</Link>
                <PriceTag priceInfo={product.price_info} size="sm" />
                <div className="product-card__footer">
                  <span className={`stock ${unavailable ? "stock--out_of_stock" : "stock--in_stock"}`}>
                    {!item.is_available
                      ? "غیرفعال شده"
                      : product.stock_status === "out_of_stock"
                        ? "ناموجود"
                        : "موجود"}
                  </span>
                  <div className="product-card__actions">
                    <button
                      type="button"
                      className="btn btn--outline btn--sm"
                      disabled={busyId === item.id}
                      onClick={() => handleRemove(item.id)}
                    >
                      {busyId === item.id ? "…" : "حذف"}
                    </button>
                    <button
                      type="button"
                      className="btn btn--primary btn--sm"
                      disabled={unavailable || busyId === `cart-${product.id}`}
                      onClick={() => handleAddToCart(product.id)}
                    >
                      {busyId === `cart-${product.id}` ? "…" : "افزودن به سبد"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default WishlistPage;
