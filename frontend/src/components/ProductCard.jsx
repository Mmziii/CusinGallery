import { useState } from "react";
import { Link } from "react-router-dom";

import useAuthStore from "../store/useAuthStore";
import { productShape } from "../utils/shapes";
import useCartStore from "../store/useCartStore";
import * as wishlistApi from "../services/wishlistApi";
import PriceTag from "./PriceTag";

/**
 * One catalog row as a card: image, name, price block, stock status,
 * add-to-cart and wishlist actions. All data comes from the product
 * object the catalog API returned -- nothing is fabricated here.
 */
function ProductCard({ product }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const addItem = useCartStore((s) => s.addItem);
  const [adding, setAdding] = useState(false);
  const [addedToWishlist, setAddedToWishlist] = useState(false);

  const outOfStock = product.stock_status === "out_of_stock";
  const imageUrl = product.primary_image?.image;

  const handleAdd = async () => {
    setAdding(true);
    await addItem(product.id, null, 1);
    setAdding(false);
  };

  // Card-level wishlist action is add-only (the true filled-state lives
  // on the product page and the wishlist page, which have the item ids
  // removal requires). Adding twice is gracefully idempotent server-side.
  const handleWishlist = async () => {
    if (!isAuthenticated || addedToWishlist) return;
    await wishlistApi.addWishlistItem(product.id);
    setAddedToWishlist(true);
  };

  return (
    <div className="product-card">
      <Link to={`/products/${product.slug}/`} className="product-card__media">
        {imageUrl ? (
          <img src={imageUrl} alt={product.primary_image?.alt_text || product.name} loading="lazy" />
        ) : (
          <div className="product-card__placeholder">تصویر ندارد</div>
        )}
        {product.price_info?.is_on_sale ? (
          <span className="product-card__sale">فروش ویژه</span>
        ) : null}
      </Link>

      <div className="product-card__body">
        <Link to={`/products/${product.slug}/`} className="product-card__name">
          {product.name}
        </Link>
        {product.brand ? <div className="product-card__brand">{product.brand.name}</div> : null}

        <PriceTag priceInfo={product.price_info} size="sm" />

        <div className="product-card__footer">
          <span className={`stock stock--${product.stock_status}`}>
            {outOfStock ? "ناموجود" : product.stock_status === "low_stock" ? "تعداد محدود" : "موجود"}
          </span>

          <div className="product-card__actions">
            <button
              type="button"
              className={`icon-btn ${addedToWishlist ? "icon-btn--active" : ""}`}
              title="افزودن به علاقه‌مندی‌ها"
              onClick={handleWishlist}
              disabled={!isAuthenticated || addedToWishlist}
            >
              {addedToWishlist ? "♥" : "♡"}
            </button>
            <button
              type="button"
              className="btn btn--primary btn--sm"
              onClick={handleAdd}
              disabled={outOfStock || adding}
            >
              {outOfStock ? "ناموجود" : adding ? "…" : "افزودن به سبد"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

ProductCard.propTypes = { product: productShape.isRequired };

export default ProductCard;
