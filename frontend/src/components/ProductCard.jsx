import { useState } from "react";
import { Link } from "react-router-dom";

import useAuthStore from "../store/useAuthStore";
import { productShape } from "../utils/shapes";
import useCartStore from "../store/useCartStore";
import * as wishlistApi from "../services/wishlistApi";
import { toast } from "../utils/toast";
import PriceTag from "./PriceTag";
import SmartImage from "./SmartImage";

/**
 * Catalog card (Part 3 redesign): badges (new / discount % / low stock /
 * out of stock), second-image crossfade on hover when a gallery exists,
 * quick add-to-cart with toast feedback, wishlist heart, crossed-out
 * compare-at price, Persian-digit Toman -- all from the catalog payload,
 * nothing fabricated.
 */
function ProductCard({ product }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const addItem = useCartStore((s) => s.addItem);
  const [adding, setAdding] = useState(false);
  const [addedToWishlist, setAddedToWishlist] = useState(false);

  const outOfStock = product.stock_status === "out_of_stock";
  const lowStock = product.stock_status === "low_stock";
  const images = product.images || [];
  const primary = product.primary_image?.image || images[0]?.image || null;
  const secondary = images.find((img) => img.image !== primary)?.image || null;

  const handleAdd = async () => {
    setAdding(true);
    const result = await addItem(product.id, null, 1);
    setAdding(false);
    if (result?.success) toast("به سبد خرید اضافه شد");
  };

  // Card-level wishlist action is add-only (the filled state lives on
  // the product page and the wishlist page, which hold the item ids
  // removal requires). Adding twice is idempotent server-side.
  const handleWishlist = async () => {
    if (!isAuthenticated || addedToWishlist) return;
    await wishlistApi.addWishlistItem(product.id);
    setAddedToWishlist(true);
    toast("به علاقه‌مندی‌ها اضافه شد");
  };

  return (
    <div className={`product-card ${outOfStock ? "product-card--oos" : ""}`}>
      <Link to={`/products/${product.slug}/`} className="product-card__media">
        {primary ? (
          <>
            <SmartImage
              image={product.primary_image}
              alt={product.primary_image?.alt_text || product.name}
              className="product-card__img product-card__img--main"
            />
            {secondary ? (
              <img
                src={secondary}
                alt=""
                aria-hidden="true"
                loading="lazy"
                className="product-card__img product-card__img--alt"
              />
            ) : null}
          </>
        ) : (
          <div className="product-card__placeholder" aria-label="تصویر ندارد">
            <img src="/brand/logo-dark.svg" alt="" className="product-card__placeholder-logo" />
          </div>
        )}

        <span className="product-card__badges">
          {product.is_new ? <span className="badge badge--new">جدید</span> : null}
          {product.price_info?.discount_percentage > 0 ? (
            <span className="badge badge--sale">{product.price_info.discount_percentage}٪</span>
          ) : null}
          {lowStock ? <span className="badge badge--low">تعداد محدود</span> : null}
          {outOfStock ? <span className="badge badge--oos">ناموجود</span> : null}
        </span>

        {!outOfStock ? (
          <button
            type="button"
            className="product-card__quick-add"
            aria-label="افزودن سریع به سبد"
            disabled={adding}
            onClick={(event) => {
              event.preventDefault();
              handleAdd();
            }}
          >
            +
          </button>
        ) : null}
      </Link>

      <div className="product-card__body">
        <Link to={`/products/${product.slug}/`} className="product-card__name">
          {product.name}
        </Link>
        {product.brand ? <div className="product-card__brand">{product.brand.name}</div> : null}

        <PriceTag priceInfo={product.price_info} size="sm" />

        <div className="product-card__footer">
          <button
            type="button"
            className={`icon-btn ${addedToWishlist ? "icon-btn--active" : ""}`}
            title="افزودن به علاقه‌مندی‌ها"
            aria-label="افزودن به علاقه‌مندی‌ها"
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
  );
}

ProductCard.propTypes = { product: productShape.isRequired };

export default ProductCard;
