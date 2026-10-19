import ProductCard from "../components/ProductCard";
import { faDigits, faDate } from "../utils/faDigits";
import useWishlistStore from "../store/useWishlistStore";
import { ContentSkeleton } from "../components/Skeletons";
import NotFound from "./NotFound";
import { normalizePhone, isValidIranianPhone } from "../utils/iranianFields";
import { usePageMeta } from "../hooks/usePageMeta";
import PropTypes from "prop-types";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import Breadcrumbs from "../components/Breadcrumbs";
import Icon from "../components/Icon";
import StarRating from "../components/StarRating";
import PriceTag from "../components/PriceTag";
import ProductGallery from "../components/ProductGallery";
import { productDetailShape } from "../utils/shapes";
import { Alert, EmptyState, ErrorState, Spinner, errorMessage } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { getProduct } from "../services/catalogApi";
import { subscribeBackInStock } from "../services/productsApi";
import * as reviewsApi from "../services/reviewsApi";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import { normalizeApiError } from "../utils/apiError";
import { trackEvent } from "../utils/behaviour";
import { recordView } from "../utils/recentlyViewed";
import { shareImageUrl } from "../utils/shareImage";
import { brandUrl } from "../utils/brands";
import { categoryUrl } from "../utils/categories";
import RecentlyViewed from "../components/RecentlyViewed";

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
          aria-label={`${faDigits(n)} ستاره`}
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
    if (!Array.isArray(myReviews)) return null;
    return myReviews.find((review) => review.product === product.id) || null;
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
          <span className="reviews__avg">{faDigits(summary.average_rating)}</span>
          <Stars value={summary.average_rating} />
          <span className="reviews__count">{faDigits(summary.count)} نظر</span>
        </div>
      ) : null}

      {isLoading ? <Spinner /> : null}
      {reviews && reviews.results?.length === 0 ? (
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
            <time>{faDate(review.created_at)}</time>
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

/** Full content stays beside the gallery; phones use native accordions. */
function ProductContentSection({ title, collapsible, children }) {
  if (collapsible) {
    return (
      <details className="product-detail__section">
        <summary><h2>{title}</h2><Icon name="chevron-down" size={18} /></summary>
        {children}
      </details>
    );
  }
  return <section className="product-detail__section"><h2>{title}</h2>{children}</section>;
}

function ProductDetailPage() {
  const { slug } = useParams();
  const isMobile = useMediaQuery("(max-width: 767px)");
  const { data: product, isLoading, error, refetch } = useAsync(() => getProduct(slug), [slug]);

  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const addItem = useCartStore((s) => s.addItem);

  const [quantity, setQuantity] = useState(1);
  const [selected, setSelected] = useState({}); // attribute name -> value
  const [added, setAdded] = useState(null);
  const wishlist = useWishlistStore();
  const wishlisted = wishlist.items.some(item => item.product.id === product?.id);
  const [wishlistBusy, setWishlistBusy] = useState(false);
  const [bisPhone, setBisPhone] = useState("");
  const [bisState, setBisState] = useState(null); // null | busy | done | error

  const images = product?.images || [];

  // Part R5 item 10: record the view in browser-local storage only.
  useEffect(() => {
    if (product?.id) recordView(product.id);
    // Privacy-friendly analytics: one product_view per product page.
    if (product?.id) trackEvent("product_view", { product_id: product.id });
  }, [product?.id]);

  // Per-product SEO/social metadata (Phase E). Values start undefined
  // and settle once the product loads; the canonical always points at
  // the slug URL (query strings like ?review=1 must not fork it).
  //
  // Part S4 item 2: the share image is the product's FIRST image as an
  // ABSOLUTE url, preferring the largest WebP variant of at least 600 px
  // wide, and the shared brand placeholder when the product has no image.
  // (Before: `${SITE_ORIGIN}${product.primary_image}` -- primary_image is
  // an object and may be absent, so the tag was never a real image.)
  const shareSource = product ? product.primary_image || product.images?.[0] || null : null;
  const ogImage = product ? shareImageUrl(shareSource) : undefined;
  usePageMeta({
    title: error?.response?.status === 404
      ? "صفحه یافت نشد"
      : product?.name
        ? faDigits(product.name)
        : undefined,
    description: product?.short_description ? faDigits(product.short_description) : undefined,
    path: `/products/${slug}/`,
    image: ogImage,
  });

  // Stage 1: the breadcrumb trail as data -- shared by the
  // visible <Breadcrumbs> and the JSON-LD BreadcrumbList
  // below. کازین گالری › آشپزخانه (the catalog root,
  // first ancestor) › … intermediate groups … › the product's
  // own category › the product.
  const crumbTrail = useMemo(() => {
    if (!product) return [];
    const trail = [{ label: "کازین گالری", to: "/" }];
    if (product.category) {
      for (const ancestor of product.category.ancestors || []) {
        trail.push({ label: faDigits(ancestor.name), to: categoryUrl(ancestor) });
      }
      trail.push({
        label: faDigits(product.category.name),
        to: categoryUrl(product.category),
      });
    }
    trail.push({ label: faDigits(product.name) });
    return trail;
  }, [product]);

  // Stage 1: JSON-LD BreadcrumbList (same trail as the visible
  // breadcrumbs) for search engines that DO run JavaScript.
  // Replaced per product, removed on unmount.
  useEffect(() => {
    if (!product) return undefined;
    const script = document.createElement("script");
    script.type = "application/ld+json";
    script.id = "breadcrumb-jsonld";
    script.textContent = JSON.stringify({
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: crumbTrail.map((crumb, index) => ({
        "@type": "ListItem",
        position: index + 1,
        name: crumb.label,
        ...(crumb.to
          ? { item: `${window.location.origin}${crumb.to}` }
          : {}),
      })),
    });
    document.head.appendChild(script);
    return () => script.remove();
  }, [product, crumbTrail]);

  // Part S4 item 2: JSON-LD Product for search engines that DO run
  // JavaScript (Google). It uses the same image as og:image, so a product
  // preview is never imageless. Replaced per product, removed on unmount.
  useEffect(() => {
    if (!product) return undefined;
    const script = document.createElement("script");
    script.type = "application/ld+json";
    script.id = "product-jsonld";
    script.textContent = JSON.stringify({
      "@context": "https://schema.org",
      "@type": "Product",
      name: product.name,
      image: [ogImage],
      description: product.short_description || undefined,
      sku: product.sku,
      brand: product.brand ? { "@type": "Brand", name: product.brand.name } : undefined,
      url: `${window.location.origin}/products/${slug}/`,
      offers: {
        "@type": "Offer",
        price: String(product.price_info?.price ?? ""),
        // Whole-Toman prices (see README).
        priceCurrency: "IRT",
        availability:
          product.stock_status === "out_of_stock"
            ? "https://schema.org/OutOfStock"
            : "https://schema.org/InStock",
      },
    });
    document.head.appendChild(script);
    return () => script.remove();
  }, [product, ogImage, slug]);

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
  const availableStock = activeVariant?.stock_quantity ?? product?.stock_quantity ?? Infinity;
  const outOfStock = stockStatus === "out_of_stock";
  useEffect(() => { setQuantity(q => Math.max(1, Math.min(q, availableStock))); }, [availableStock, activeVariant?.id]);

  useEffect(() => {
    setSelected({});
    setQuantity(1);
    setAdded(null);
  }, [slug]);


  if (isLoading) return <ContentSkeleton label="در حال دریافت محصول…" />;
  if (error?.response?.status === 404) return <NotFound />;
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
    if (!isAuthenticated || wishlistBusy) return;
    setWishlistBusy(true);
    await wishlist.toggle(product.id);
    setWishlistBusy(false);
  };

  return (
    <div className="product-detail">
      {/* Part S2 item 7: breadcrumbs on the product page.
          Stage 1: every trail starts کازین گالری ›
          آشپزخانه, then the deeper levels of the tree. */}
      <Breadcrumbs items={crumbTrail} />
      <div className="product-detail__body">
        <div className="product-detail__gallery">
          {/* Part S5 item 3: main image + thumbnail row (cross-fade, keyboard,
              swipe, scroll-snap) -- every image still goes through the shared
              SmartImage, so a broken one shows the placeholder. */}
          <ProductGallery images={images} name={faDigits(product.name)} />
          {product.sku ? (
            <p className="product-detail__sku">کد کالا: <bdi dir="ltr">{faDigits(product.sku)}</bdi></p>
          ) : null}
        </div>

        <div className="product-detail__info">
          <h1>{faDigits(product.name)}</h1>
          {product.brand ? (
            <div className="product-detail__brand">
              {product.brand.slug ? <Link to={brandUrl(product.brand.slug)}>برند: {faDigits(product.brand.name)}</Link> : `برند: ${faDigits(product.brand.name)}`}
            </div>
          ) : null}
          {product.short_description ? <p className="product-detail__short">{faDigits(product.short_description)}</p> : null}

          <PriceTag priceInfo={displayPrice} size="lg" />

          <span className={`stock stock--${stockStatus}`}>
            {outOfStock ? "ناموجود" : stockStatus === "low_stock" ? "تعداد محدود" : "موجود در انبار"}
          </span>

          {hasVariants ? (
            <div className="variant-select">
              {attributeOptions.map(({ attribute, values }) => (
                <div key={attribute} className="variant-select__group">
                  <span>{faDigits(attribute)}:</span>
                  {values.map((value) => (
                    <button
                      key={value}
                      type="button"
                      className={selected[attribute] === value ? "chip chip--active" : "chip"}
                      onClick={() => setSelected((s) => ({ ...s, [attribute]: value }))}
                    >
                      {faDigits(value)}
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
            <div className="qty-picker" hidden={outOfStock}>
              <button type="button" onClick={() => setQuantity((q) => Math.max(1, q - 1))} aria-label="کاهش"><Icon name="minus" size={16} /></button>
              <span>{faDigits(quantity)}</span>
              <button type="button" disabled={quantity >= availableStock} onClick={() => setQuantity((q) => Math.min(availableStock, q + 1))} aria-label="افزایش"><Icon name="plus" size={16} /></button>
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
                <p className="muted">این کالا فعلاً موجود نیست. شمارهٔ موبایل‌تان را بگذارید تا وقتی موجود شد خبرتان کنیم.</p>
                <div className="back-in-stock__row">
                  <input
                    type="text"
                    dir="ltr"
                    inputMode="numeric"
                    placeholder="شماره موبایل"
                    maxLength={20}
                    value={bisPhone}
                    onChange={(e) => setBisPhone(normalizePhone(e.target.value))}
                    aria-label="شماره موبایل برای اطلاع‌رسانی موجودی"
                  />
                  <button
                    type="button"
                    className="btn btn--outline"
                    disabled={bisState === "busy" || !isValidIranianPhone(bisPhone)}
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
              aria-pressed={wishlisted}
              disabled={!isAuthenticated || wishlistBusy}
              title={wishlisted ? "حذف از علاقه‌مندی‌ها" : "افزودن به علاقه‌مندی‌ها"}
              aria-label={wishlisted ? "حذف از علاقه‌مندی‌ها" : "افزودن به علاقه‌مندی‌ها"}
            >
              <Icon name="heart" filled={wishlisted} size={20} />
            </button>
          </div>

          {added && added.error ? <Alert>{errorMessage(added.error)}</Alert> : null}
          {typeof added === "string" ? <Alert kind="success">{added}</Alert> : null}

          <div className="product-detail__content">
            <ProductContentSection title="توضیحات" collapsible={isMobile}>
              <p className="product-detail__description">
                {faDigits(product.description || product.short_description || "توضیحاتی ثبت نشده است.")}
              </p>
            </ProductContentSection>
            {product.specifications?.length ? (
              <ProductContentSection title="مشخصات" collapsible={isMobile}>
                <table className="specs">
                  <tbody>
                    {product.specifications.map((spec) => (
                      <tr key={spec.attribute}>
                        <th scope="row">{faDigits(spec.attribute)}</th>
                        <td>{faDigits(spec.values.join("، "))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </ProductContentSection>
            ) : null}
          </div>
        </div>
      </div>

      {product.related_products?.length ? (
        <section className="product-detail__related">
          <h2>محصولات مرتبط</h2>
          <div className="related-grid">
            {product.related_products.map((related) => (
              <ProductCard key={related.id} product={related} />
            ))}
          </div>
        </section>
      ) : null}

      <ReviewSection product={product} />

      {/* Part R5 item 10: browser-local, server knows nothing about it */}
      <RecentlyViewed excludeId={product.id} />

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
ProductContentSection.propTypes = {
  title: PropTypes.string.isRequired,
  collapsible: PropTypes.bool.isRequired,
  children: PropTypes.node.isRequired,
};

export default ProductDetailPage;
