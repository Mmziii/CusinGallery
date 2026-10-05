import { SITE_ORIGIN, usePageMeta } from "../hooks/usePageMeta";
import PropTypes from "prop-types";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import Icon from "../components/Icon";
import StarRating from "../components/StarRating";
import PriceTag from "../components/PriceTag";
import SmartImage from "../components/SmartImage";
import { productDetailShape } from "../utils/shapes";
import { Alert, EmptyState, ErrorState, Spinner, errorMessage } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { getProduct } from "../services/catalogApi";
import { subscribeBackInStock } from "../services/productsApi";
import * as reviewsApi from "../services/reviewsApi";
import * as wishlistApi from "../services/wishlistApi";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import { normalizeApiError } from "../utils/apiError";
import { formatPrice } from "../utils/formatPrice";

function Stars({ value, size = "md" }) {
  // Part R2: SVG stars (no text glyphs).
  return <StarRating rating={Math.round(value || 0)} size={size === "lg" ? 20 : 16} />;
}

function RatingInput({ value, onChange }) {
  return (
    <div className="rating-input" role="radiogroup" aria-label="امتیاز">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          className={n <= value ? "star star--on" : "star"}
          onClick={() => onChange(n)}
        >
          <Icon name="star" size={22} filled={n <= value} />
        </button>
      ))}
    </div>
  );
}

function ReviewSection({ product }) {
  const { isAuthenticated } = useAuthStore();
  const [page, setPage] = useState(1);
  const { data: summary } = useAsync(() => reviewsApi.fetchProductReviewSummary(product.id), [product.id]);
  const { data: reviews, isLoading } = useAsync(
    () => reviewsApi.fetchProductReviews(product.id, { page }),
    [product.id, page]
  );
  // The "my review" state comes from the authenticated user's own list.
  const { data: myReviews, refetch: refetchMyReviews } = useAsync(
    () => (isAuthenticated ? reviewsApi.fetchMyReviews() : Promise.resolve(null)),
    [isAuthenticated, product.id]
  );

  const myReview = useMemo(() => {
    if (!myReviews?.results) return null;
    return myReviews.results.find((review) => review.product === product.id) || null;
  }, [myReviews, product.id]);

  const [form, setForm] = useState({ rating: 0, title: "", body: "" });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);
  const [formOk, setFormOk] = useState(null);

  useEffect(() => {
    if (myReview) setForm({ rating: myReview.rating, title: myReview.title, body: myReview.body });
  }, [myReview]);

  const submit = async (event) => {
    event.preventDefault();
    setFormError(null);
    setFormOk(null);
    if (!form.rating) {
      setFormError("لطفاً امتیاز خود را انتخاب کنید.");
      return;
    }
    setSubmitting(true);
    try {
      if (myReview) {
        await reviewsApi.updateReview(myReview.id, form);
        setFormOk("نظر شما ویرایش شد و پس از تأیید نمایش داده می‌شود.");
      } else {
        await reviewsApi.createReview({ product_id: product.id, ...form });
        setFormOk("نظر شما ثبت شد و پس از تأیید نمایش داده می‌شود.");
      }
      // Refresh "my review" so the form switches to edit mode instead of
      // offering (and then 400ing) a duplicate submission.
      refetchMyReviews();
    } catch (err) {
      setFormError(errorMessage(normalizeApiError(err)));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="reviews" id="reviews">
      <h2>نظرات کاربران</h2>

      {summary && summary.count > 0 ? (
        <div className="reviews__summary">
          <span className="reviews__avg">{summary.average_rating}</span>
          <Stars value={summary.average_rating} />
          <span className="reviews__count">{summary.count} نظر</span>
        </div>
      ) : null}

      {isLoading ? <Spinner /> : null}
      {reviews && reviews.results.length === 0 ? (
        <EmptyState title="هنوز نظری برای این محصول ثبت نشده است." />
      ) : null}

      <div className="reviews__list">
        {(reviews?.results || []).map((review) => (
          <article key={review.id} className="review">
            <header>
              <strong>{review.username}</strong>
              <Stars value={review.rating} size="sm" />
              {review.is_verified_purchase ? (
                <span className="review__verified">خرید تأیید شده</span>
              ) : null}
            </header>
            {review.title ? <h4>{review.title}</h4> : null}
            {review.body ? <p>{review.body}</p> : null}
            <time>{new Date(review.created_at).toLocaleDateString("fa-IR")}</time>
          </article>
        ))}
      </div>

      {reviews && reviews.next ? (
        <button type="button" className="btn btn--outline btn--sm" onClick={() => setPage((p) => p + 1)}>
          نظرات بیشتر
        </button>
      ) : null}

      <div className="review-form-wrap">
        <h3>{myReview ? "ویرایش نظر شما" : "نظر خود را بنویسید"}</h3>
        {!isAuthenticated ? (
          <p>
            برای ثبت نظر <Link to="/login/">وارد شوید</Link>.
          </p>
        ) : (
          <form className="review-form" onSubmit={submit}>
            <RatingInput value={form.rating} onChange={(rating) => setForm((f) => ({ ...f, rating }))} />
            <input
              type="text"
              placeholder="عنوان نظر (اختیاری)"
              value={form.title}
              maxLength={200}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
            <textarea
              placeholder="متن نظر…"
              rows={4}
              value={form.body}
              onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))}
            />
            <Alert>{formError}</Alert>
            {formOk ? <Alert kind="success">{formOk}</Alert> : null}
            <button type="submit" className="btn btn--primary" disabled={submitting}>
              {submitting ? "در حال ارسال…" : myReview ? "به‌روزرسانی نظر" : "ثبت نظر"}
            </button>
          </form>
        )}
      </div>
    </section>
  );
}

function ProductDetailPage() {
  const { slug } = useParams();
  const { data: product, isLoading, error, refetch } = useAsync(() => getProduct(slug), [slug]);

  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const addItem = useCartStore((s) => s.addItem);

  const [activeImage, setActiveImage] = useState(0);
  const [quantity, setQuantity] = useState(1);
  const [selected, setSelected] = useState({}); // attribute name -> value
  const [added, setAdded] = useState(null);
  const [wishlisted, setWishlisted] = useState(false);
  const [bisPhone, setBisPhone] = useState("");
  const [bisState, setBisState] = useState(null); // null | busy | done | error

  const images = product?.images || [];

  // Per-product SEO/social metadata (Phase E). Values start undefined
  // and settle once the product loads; the canonical always points at
  // the slug URL (query strings like ?review=1 must not fork it).
  usePageMeta({
    title: product?.name,
    description: product?.short_description || undefined,
    path: `/products/${slug}/`,
    image: product?.primary_image ? `${SITE_ORIGIN}${product.primary_image}` : undefined,
  });

  // Group variants by attribute for the option buttons.
  const attributeOptions = useMemo(() => {
    if (!product?.variants?.length) return [];
    const groups = {};
    const order = [];
    product.variants.forEach((variant) => {
      variant.attribute_values.forEach((av) => {
        if (!groups[av.attribute]) {
          groups[av.attribute] = new Set();
          order.push(av.attribute);
        }
        groups[av.attribute].add(av.value);
      });
    });
    return order.map((attribute) => ({ attribute, values: [...groups[attribute]] }));
  }, [product]);

  const activeVariant = useMemo(() => {
    if (!product?.variants?.length) return null;
    if (Object.keys(selected).length < attributeOptions.length) return null;
    return (
      product.variants.find((variant) =>
        variant.attribute_values.every((av) => selected[av.attribute] === av.value)
      ) || null
    );
  }, [product, selected, attributeOptions]);

  const hasVariants = Boolean(product?.variants?.length);
  const displayPrice = activeVariant ? activeVariant.price_info : product?.price_info;
  const stockStatus = activeVariant ? activeVariant.stock_status : product?.stock_status;
  const outOfStock = stockStatus === "out_of_stock";

  useEffect(() => {
    setActiveImage(0);
    setSelected({});
    setQuantity(1);
    setAdded(null);
  }, [slug]);

  useEffect(() => {
    if (!isAuthenticated || !product) return;
    wishlistApi.checkWishlisted(product.id).then(setWishlisted).catch(() => {});
  }, [isAuthenticated, product]);

  if (isLoading) return <Spinner label="در حال دریافت محصول…" />;
  if (error) return <ErrorState message={errorMessage(normalizeApiError(error))} onRetry={refetch} />;
  if (!product) return null;

  const handleAdd = async () => {
    setAdded(null);
    const result = await addItem(product.id, activeVariant?.id ?? null, quantity);
    if (result.success) {
      setAdded("به سبد خرید اضافه شد.");
    } else {
      setAdded({ error: result.error });
    }
  };

  const handleWishlist = async () => {
    if (!isAuthenticated || wishlisted) return;
    try {
      await wishlistApi.addWishlistItem(product.id);
      setWishlisted(true);
    } catch {
      /* surfaced via cart-style toasts elsewhere; keep silent here */
    }
  };

  return (
    <div className="product-detail">
      <div className="product-detail__gallery">
        <div
          className="product-detail__main-image"
          onClick={(e) => e.currentTarget.querySelector("img")?.classList.toggle("is-zoomed")}
        >
          {/* SmartImage (Part R1): missing/broken gallery image -> shared placeholder */}
          <SmartImage
            image={images[activeImage] || null}
            alt={images[activeImage]?.alt_text || product.name}
            className="product-detail__main-img"
          />
        </div>
        {images.length > 1 ? (
          <div className="product-detail__thumbs">
            {images.map((image, index) => (
              <button
                key={image.id}
                type="button"
                className={index === activeImage ? "thumb thumb--active" : "thumb"}
                onClick={() => setActiveImage(index)}
              >
                <SmartImage image={image} alt={image.alt_text || `${product.name} ${index + 1}`} />
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <div className="product-detail__info">
        <nav className="breadcrumb">
          <Link to="/">خانه</Link> /{" "}
          {product.category ? (
            <>
              <Link to={`/shop/?category=${encodeURIComponent(product.category.slug)}`}>
                {product.category.name}
              </Link>{" "}
              /{" "}
            </>
          ) : null}
          <span>{product.name}</span>
        </nav>

        <h1>{product.name}</h1>
        {product.brand ? <div className="product-detail__brand">برند: {product.brand.name}</div> : null}
        {product.short_description ? <p className="product-detail__short">{product.short_description}</p> : null}

        <PriceTag priceInfo={displayPrice} size="lg" />

        <span className={`stock stock--${stockStatus}`}>
          {outOfStock ? "ناموجود" : stockStatus === "low_stock" ? "تعداد محدود" : "موجود در انبار"}
        </span>

        {hasVariants ? (
          <div className="variant-select">
            {attributeOptions.map(({ attribute, values }) => (
              <div key={attribute} className="variant-select__group">
                <span>{attribute}:</span>
                {values.map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={selected[attribute] === value ? "chip chip--active" : "chip"}
                    onClick={() => setSelected((s) => ({ ...s, [attribute]: value }))}
                  >
                    {value}
                  </button>
                ))}
              </div>
            ))}
            {Object.keys(selected).length === attributeOptions.length && !activeVariant ? (
              <Alert>این ترکیب گزینه‌ها موجود نیست.</Alert>
            ) : null}
          </div>
        ) : null}

        <div className="product-detail__buy">
          <div className="qty-picker">
            <button type="button" onClick={() => setQuantity((q) => Math.max(1, q - 1))} aria-label="کاهش"><Icon name="minus" size={16} /></button>
            <span>{quantity}</span>
            <button type="button" onClick={() => setQuantity((q) => q + 1)} aria-label="افزایش"><Icon name="plus" size={16} /></button>
          </div>

          <button
            type="button"
            className="btn btn--primary"
            onClick={handleAdd}
            disabled={outOfStock || (hasVariants && !activeVariant)}
          >
            {outOfStock ? "ناموجود" : hasVariants && !activeVariant ? "انتخاب گزینه‌ها" : "افزودن به سبد خرید"}
          </button>
        {outOfStock ? (
          <div className="back-in-stock">
            <p className="muted">کیف را جا نگذارید: شمارهٔ موبایل بگذارید تا به محض موجودشدن پیامک بزنیم.</p>
            <div className="back-in-stock__row">
              <input
                type="text"
                dir="ltr"
                inputMode="numeric"
                placeholder="09xxxxxxxxx"
                maxLength={11}
                value={bisPhone}
                onChange={(e) => setBisPhone(e.target.value)}
                aria-label="شماره موبایل برای اطلاع‌رسانی موجودی"
              />
              <button
                type="button"
                className="btn btn--outline"
                disabled={bisState === "busy"}
                onClick={async () => {
                  setBisState("busy");
                  try {
                    await subscribeBackInStock(product.id, activeVariant?.id ?? null, bisPhone.trim());
                    setBisState("done");
                  } catch (err) {
                    setBisState(errorMessage(normalizeApiError(err)));
                  }
                }}
              >
                اطلاع به من
              </button>
            </div>
            {bisState === "done" ? (
              <p className="field-help">ثبت شد؛ به محض موجودشدن اطلاع‌رسانی می‌شود.</p>
            ) : bisState && bisState !== "busy" ? (
              <p className="field-help field-help--error">{bisState}</p>
            ) : null}
          </div>
        ) : null}

          <button
            type="button"
            className={`icon-btn icon-btn--lg ${wishlisted ? "icon-btn--active" : ""}`}
            onClick={handleWishlist}
            disabled={!isAuthenticated || wishlisted}
            title="علاقه‌مندی"
          >
            <Icon name="heart" filled={wishlisted} size={20} />
          </button>
        </div>

        {added && added.error ? <Alert>{errorMessage(added.error)}</Alert> : null}
        {typeof added === "string" ? <Alert kind="success">{added}</Alert> : null}
      </div>

      <div className="product-detail__extra">
        <div className="product-detail__assurances">
          <div><strong>ارسال:</strong> عادی ۳ تا ۵ روز / اکسپرس ۱ روزه / دریافت حضوری</div>
          <div><strong>بسته‌بندی:</strong> ضدضربه برای ظروف شکستنی و بلور</div>
          <div><strong>مرجوعی:</strong> تا ۷ روز با شرایط درج‌شده در «ارسال و مرجوعی»</div>
        </div>
        <section>
          <h2>توضیحات</h2>
          <p className="product-detail__description">
            {product.description || product.short_description || "توضیحاتی ثبت نشده است."}
          </p>
        </section>

        {product.specifications?.length ? (
          <section>
            <h2>مشخصات</h2>
            <table className="specs">
              <tbody>
                {product.specifications.map((spec) => (
                  <tr key={spec.attribute}>
                    <th>{spec.attribute}</th>
                    <td>{spec.values.join("، ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ) : null}

        {product.related_products?.length ? (
          <section>
            <h2>محصولات مرتبط</h2>
            <div className="related-grid">
              {product.related_products.map((related) => (
                <Link key={related.id} to={`/products/${related.slug}/`} className="related-card">
                  <SmartImage image={related.primary_image || null} alt={related.name} />
                  <span>{related.name}</span>
                  <span className="related-card__price">{formatPrice(related.price_info.price)} تومان</span>
                </Link>
              ))}
            </div>
          </section>
        ) : null}
      </div>

      <ReviewSection product={product} />

      <div className="product-detail__stickybar">
        <PriceTag priceInfo={displayPrice} size="md" />
        <button
          type="button"
          className="btn btn--primary"
          onClick={handleAdd}
          disabled={outOfStock || (hasVariants && !activeVariant)}
        >
          {outOfStock ? "ناموجود" : "افزودن به سبد خرید"}
        </button>
      </div>
    </div>
  );
}

Stars.propTypes = { value: PropTypes.number, size: PropTypes.oneOf(["sm", "md", "lg"]) };
RatingInput.propTypes = { value: PropTypes.number.isRequired, onChange: PropTypes.func.isRequired };
ReviewSection.propTypes = { product: productDetailShape.isRequired };

export default ProductDetailPage;
