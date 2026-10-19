import { brandUrl } from "../utils/brands";
import { faDigits } from "../utils/faDigits";
import useWishlistStore from "../store/useWishlistStore";
import { useState } from "react";
import { Link } from "react-router-dom";

import useAuthStore from "../store/useAuthStore";
import { productShape } from "../utils/shapes";
import useCartStore from "../store/useCartStore";
import { toast } from "../utils/toast";
import Icon from "./Icon";
import PriceTag from "./PriceTag";
import SmartImage from "./SmartImage";
import { useMediaQuery } from "../hooks/useMediaQuery";

/**
 * Catalog card (Part 3 redesign): badges (new / discount % / low stock /
 * out of stock), second-image crossfade on hover when a gallery exists,
 * quick add-to-cart with toast feedback, wishlist heart, crossed-out
 * compare-at price, Persian-digit Toman -- all from the catalog payload,
 * nothing fabricated.
 *
 * Audit 19 item 1 -- compact mode (`<= 767px`): the phone grid is two
 * columns wide, so the card drops to a square image with the badges as
 * small chips, a 2-line name, a 1-line brand line (its space is reserved
 * even when the product has none), the old price struck through next to
 * a bold final price pinned to the card's bottom, a round cart-plus
 * button (36px tap target) instead of a full-width text button, and the
 * wishlist heart on the image's opposite corner (32px). Out-of-stock
 * products show «موجود شد خبرم کن» as a small text link instead of an
 * add button. The desktop markup below is unchanged.
 */
function ProductCard({ product }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const addItem = useCartStore((s) => s.addItem);
  const [adding, setAdding] = useState(false);
  const wishlist = useWishlistStore();
  const addedToWishlist = wishlist.items.some(item => item.product.id === product.id);
  const [wishlistBusy, setWishlistBusy] = useState(false);
  // Part S4 item 1: the hover cross-fade image is decorative -- when its
  // file is missing it hides itself silently (no broken-image icon, no
  // placeholder: the primary image above it is the real one).
  const [altFailed, setAltFailed] = useState(false);
  // The phone layout is a different card, not just different CSS: the
  // add-to-cart control and the wishlist heart change place and shape.
  const compact = useMediaQuery("(max-width: 767px)");

  const outOfStock = product.stock_status === "out_of_stock";
  const lowStock = product.stock_status === "low_stock";
  const images = product.images || [];
  const primary = product.primary_image?.image || images[0]?.image || null;
  const secondary = images.find((img) => img.image !== primary)?.image || null;
  const productHref = `/products/${product.slug}/`;
  const discountPercentage = product.price_info?.discount_percentage || (
    product.price_info?.compare_at_price > product.price_info?.price
      ? Math.floor((product.price_info.compare_at_price - product.price_info.price) * 100 / product.price_info.compare_at_price)
      : 0
  );

  const handleAdd = async () => {
    setAdding(true);
    const result = await addItem(product.id, null, 1);
    setAdding(false);
    // Part S2 item 6: toast feedback with a direct view-cart action.
    // Compact mode keeps it shorter -- on a phone the toast is read at a
    // glance, and the action link is what the shopper taps.
    if (result?.success) {
      toast(compact ? "به سبد اضافه شد" : "به سبد خرید اضافه شد", "success", { label: "مشاهده سبد", to: "/cart/" });
    } else if (result?.error) {
      toast(result.error.message || "افزودن به سبد انجام نشد.", "error");
    }
  };

  // Shared item ids let cards toggle the same state as the header and wishlist.
  const handleWishlist = async () => {
    if (!isAuthenticated || wishlistBusy) return;
    setWishlistBusy(true);
    await wishlist.toggle(product.id);
    setWishlistBusy(false);
  };

  const wishlistButton = (extraClass) => (
    <button
      type="button"
      className={`icon-btn ${extraClass} ${addedToWishlist ? "icon-btn--active" : ""}`}
      title={addedToWishlist ? "حذف از علاقه‌مندی‌ها" : "افزودن به علاقه‌مندی‌ها"}
      aria-label={addedToWishlist ? "حذف از علاقه‌مندی‌ها" : "افزودن به علاقه‌مندی‌ها"}
      onClick={(event) => {
        // Cards can host the heart INSIDE the media <Link>; a tap must
        // toggle the wishlist, never navigate to the product.
        event.preventDefault();
        handleWishlist();
      }}
      aria-pressed={addedToWishlist}
      disabled={!isAuthenticated || wishlistBusy}
    >
      <Icon name="heart" filled={addedToWishlist} size={18} />
    </button>
  );

  const badges = (
    <span className="product-card__badges">
      {product.is_new ? <span className="badge badge--new">جدید</span> : null}
      {discountPercentage > 0 ? (
        <span className="badge badge--sale">{faDigits(discountPercentage)}٪</span>
      ) : null}
      {lowStock ? <span className="badge badge--low">تعداد محدود</span> : null}
      {outOfStock ? <span className="badge badge--oos">ناموجود</span> : null}
    </span>
  );

  if (compact) {
    return (
      <div className={`product-card product-card--compact ${outOfStock ? "product-card--oos" : ""}`}>
        {/* The heart is a sibling of the media link, not a child: on the
            phone it sits over the image's top-inline-end corner, opposite
            the badge corner, and a tap must not open the product. */}
        <div className="product-card__media-wrap">
          <Link to={productHref} className="product-card__media">
            <SmartImage
              image={product.primary_image || { image: primary }}
              alt={faDigits(product.primary_image?.alt_text || product.name)}
              className="product-card__img product-card__img--main"
            />
            {badges}
          </Link>
          {wishlistButton("product-card__heart")}
        </div>

        <div className="product-card__body">
          <Link to={productHref} className="product-card__name">
            {faDigits(product.name)}
          </Link>
          {/* The brand line is rendered even when the product has none: its
              height is reserved so every card in a row keeps the same
              rhythm and the prices below stay aligned. */}
          <div className="product-card__brand">
            {product.brand?.slug ? <Link to={brandUrl(product.brand.slug)}>{faDigits(product.brand.name)}</Link> : faDigits(product.brand?.name) || "\u00a0"}
          </div>

          {/* Price + action share the LAST row: the bold final price is
              pinned to the card bottom (so prices line up across a row) and
              the round add-to-cart button sits in the card's bottom corner. */}
          <div className="product-card__footer">
            <PriceTag priceInfo={product.price_info} size="sm" />
            {outOfStock ? (
              <Link to={productHref} className="product-card__notify">
                موجود شد خبرم کن
              </Link>
            ) : (
              <button
                type="button"
                className="product-card__add-icon"
                aria-label="افزودن به سبد"
                title="افزودن به سبد"
                disabled={adding}
                onClick={handleAdd}
              >
                <Icon name={adding ? "check" : "cart-plus"} size={18} />
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`product-card ${outOfStock ? "product-card--oos" : ""}`}>
      <Link to={productHref} className="product-card__media">
        {/* SmartImage (Part R1) renders the shared brand placeholder when the
            product has no image or the file 404s (onError). */}
        <SmartImage
          image={product.primary_image || { image: primary }}
          alt={faDigits(product.primary_image?.alt_text || product.name)}
          className="product-card__img product-card__img--main"
        />
        {/* @catalog-img-allowed: reviewed exception to the
            assets.guard.test.js rule -- this layer is decorative (the
            primary image above it is the real one), so it renders a raw
            <img> and hides itself silently on error instead of showing the
            shared placeholder. */}
        {secondary && !altFailed ? (
          <img
            src={secondary}
            alt=""
            aria-hidden="true"
            loading="lazy"
            className="product-card__img product-card__img--alt"
            onError={() => setAltFailed(true)}
          />
        ) : null}

        {badges}

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
            <Icon name="plus" size={18} />
          </button>
        ) : null}
      </Link>

      <div className="product-card__body">
        <Link to={productHref} className="product-card__name">
          {faDigits(product.name)}
        </Link>
        <div className="product-card__brand">
          {product.brand?.slug ? <Link to={brandUrl(product.brand.slug)}>{faDigits(product.brand.name)}</Link> : faDigits(product.brand?.name) || "\u00a0"}
        </div>

        <PriceTag priceInfo={product.price_info} size="sm" />

        <div className="product-card__footer">
          {wishlistButton("")}
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
