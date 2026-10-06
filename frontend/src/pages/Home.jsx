import PropTypes from "prop-types";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import BrandTiles from "../components/BrandTiles";
import Icon from "../components/Icon";
import ProductCard from "../components/ProductCard";
import RecentlyViewed from "../components/RecentlyViewed";
import StarRating from "../components/StarRating";
import SmartImage from "../components/SmartImage";
import { CardRowSkeleton, HeroSkeleton } from "../components/Skeletons";
import { ErrorState } from "../components/ui";
import { usePageMeta } from "../hooks/usePageMeta";
import useReveal from "../hooks/useReveal";
import { useAsync } from "../hooks/useAsync";
import { bannerShape } from "../utils/shapes";
import { normalizeApiError } from "../utils/apiError";
import { formatPrice } from "../utils/formatPrice";
import { fetchBanners, fetchDailyDeals } from "../services/bannersApi";
import { getCategoryTree, listProducts } from "../services/catalogApi";
import { fetchProductReviews } from "../services/reviewsApi";

/**
 * Homepage (Part 3 redesign): full-width hero slider fed by the banners
 * admin, trust strip, category tiles, daily-deal feature block with
 * countdown, curated rows, a short brand story and review highlights.
 * Everything stays API-driven and silently skips absent sections.
 */
function HeroSlider({ banners, isLoading }) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const touchX = useRef(null);

  useEffect(() => {
    if (paused || banners.length <= 1) return undefined;
    const timer = setInterval(() => setIndex((i) => (i + 1) % banners.length), 6000);
    return () => clearInterval(timer);
  }, [paused, banners.length]);

  if (isLoading) return <HeroSkeleton />;
  if (banners.length === 0) return null;

  const go = (delta) => setIndex((i) => (i + delta + banners.length) % banners.length);

  return (
    <section
      className="hero"
      aria-roledescription="اسلایدر"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onTouchStart={(e) => {
        setPaused(true);
        touchX.current = e.touches[0].clientX;
      }}
      onTouchEnd={(e) => {
        setPaused(false);
        if (touchX.current !== null) {
          const dx = e.changedTouches[0].clientX - touchX.current;
          if (dx > 48) go(-1); // swipe: RTL-aware (visual left/right irrelevant)
          if (dx < -48) go(1);
          touchX.current = null;
        }
      }}
    >
      <div className="hero__track" style={{ transform: `translateX(${index * 100}%)` }}>
        {banners.map((banner, i) => (
          <div
            key={banner.id}
            className={`hero__slide ${i === index ? "is-active" : ""}`}
            aria-hidden={i !== index}
          >
            {/* Part S4 item 1: a slide with no image (or a broken one)
                shows the shared brand placeholder in the same area. */}
            <SmartImage
              image={banner.image ? banner : null}
              alt={banner.title || ""}
              eager
              sizes="100vw"
            />
            <div className="hero__overlay">
              <div className="hero__copy container">
                <h1>{banner.title}</h1>
                {banner.subtitle ? <p>{banner.subtitle}</p> : null}
                {banner.cta_url ? (
                  <Link className="btn btn--gold" to={banner.cta_url}>
                    {banner.cta_text || "مشاهده"}
                  </Link>
                ) : null}
              </div>
            </div>
          </div>
        ))}
      </div>
      {banners.length > 1 ? (
        <>
          <button type="button" className="hero__arrow hero__arrow--prev" aria-label="اسلاید قبلی" onClick={() => go(-1)}>
            <Icon name="chevron-right" size={20} />
          </button>
          <button type="button" className="hero__arrow hero__arrow--next" aria-label="اسلاید بعدی" onClick={() => go(1)}>
            <Icon name="chevron-left" size={20} />
          </button>
          <div className="hero__dots" role="tablist" aria-label="اسلایدها">
            {banners.map((banner, i) => (
              <button
                key={banner.id}
                type="button"
                role="tab"
                aria-selected={i === index}
                aria-label={`اسلاید ${i + 1}`}
                className={i === index ? "is-active" : ""}
                onClick={() => setIndex(i)}
              />
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}

function TrustStrip() {
  const ref = useReveal();
  const items = [
    ["check", "کالای اصل و تضمین سلامت"],
    ["box", "بسته‌بندی ضدضربه برای ظروف شکستنی"],
    ["truck", "ارسال سریع به سراسر ایران"],
    ["lock", "پرداخت امن اینترنتی"],
    ["undo", "مرجوعی آسان تا ۷ روز"],
  ];
  return (
    <div className="trust-strip reveal" ref={ref}>
      <div className="container trust-strip__inner">
        {items.map(([icon, label]) => (
          <div key={label} className="trust-strip__item">
            <Icon name={icon} size={18} />
            <span>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Countdown({ endsAt, serverNow }) {
  const [now, setNow] = useState(() => new Date(serverNow).getTime());
  useEffect(() => {
    const drift = Date.now() - new Date(serverNow).getTime();
    const timer = setInterval(() => setNow(Date.now() - drift), 1000);
    return () => clearInterval(timer);
  }, [serverNow]);

  const left = Math.max(0, new Date(endsAt).getTime() - now);
  if (left === 0) return <span className="countdown is-over">پایان پیشنهاد</span>;
  const hours = Math.floor(left / 3600000);
  const minutes = Math.floor((left % 3600000) / 60000);
  const seconds = Math.floor((left % 60000) / 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return (
    <span className="countdown" dir="ltr" aria-label="زمان باقی‌مانده">
      {formatPrice(hours)}:{pad(minutes)}:{pad(seconds)}
    </span>
  );
}

function DailyDealsSection() {
  const ref = useReveal();
  const { data, isLoading, error } = useAsync(() => fetchDailyDeals(), []);

  if (isLoading) return null;
  if (error || !data?.results?.length) return null;

  return (
    <section className="section section--dark reveal" ref={ref}>
      <div className="container">
        <div className="section__head">
          <h2>پیشنهاد امروز</h2>
          <span className="section__rule" aria-hidden="true" />
        </div>
        <div className="deals-grid">
          {data.results.map((deal) => (
            <Link key={deal.id} to={`/products/${deal.product.slug}/`} className="deal-card">
              <SmartImage image={deal.product.primary_image || null} alt={deal.product.name} />
              <div className="deal-card__body">
                <div className="deal-card__name">{deal.product.name}</div>
                <div className="deal-card__prices">
                  <span className="deal-card__sale">{formatPrice(deal.sale_price)} تومان</span>
                  {deal.product.price_info?.price > deal.sale_price ? (
                    <s className="deal-card__regular">{formatPrice(deal.product.price_info.price)}</s>
                  ) : null}
                </div>
                <Countdown endsAt={deal.ends_at} serverNow={data.server_now} />
              </div>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

function ProductRow({ title, params }) {
  const ref = useReveal();
  const { data, isLoading, error, refetch } = useAsync(() => listProducts(params), [JSON.stringify(params)]);

  if (isLoading)
    return (
      <section className="section container">
        <div className="section__head"><h2>{title}</h2></div>
        <CardRowSkeleton />
      </section>
    );
  if (error) return <ErrorState message={normalizeApiError(error).message} onRetry={refetch} />;
  if (!data?.results?.length) return null;

  return (
    <section className="section container reveal" ref={ref}>
      <div className="section__head">
        <h2>{title}</h2>
        <span className="section__rule" aria-hidden="true" />
        <Link to="/shop/">مشاهده همه</Link>
      </div>
      <div className="product-grid">
        {data.results.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
    </section>
  );
}

function ReviewHighlights({ products }) {
  const ref = useReveal();
  const { data } = useAsync(async () => {
    const lists = await Promise.all(
      products.slice(0, 3).map((product) =>
        fetchProductReviews(product.id, { page_size: 1 }).then((res) => ({
          product,
          review: res.results?.[0] || null,
        })).catch(() => ({ product, review: null }))
      )
    );
    return lists.filter((entry) => entry.review);
  }, [products.map((p) => p.id).join(",")]);

  if (!data?.length) return null;
  return (
    <section className="section container reveal" ref={ref}>
      <div className="section__head">
        <h2>از زبان خریداران</h2>
        <span className="section__rule" aria-hidden="true" />
      </div>
      <div className="review-highlights">
        {data.map(({ product, review }) => (
          <blockquote key={product.id} className="review-highlight">
            <p>«{review.body || review.title}»</p>
            <footer>
              {review.rating ? <StarRating rating={review.rating} /> : null}
              <cite>خریدارِ {product.name}</cite>
            </footer>
          </blockquote>
        ))}
      </div>
    </section>
  );
}

function BrandStory() {
  const ref = useReveal();
  return (
    <section className="section section--story reveal" ref={ref}>
      <div className="container section--story__inner">
        <img src="/brand/lockup.svg" alt="CusinGallery" className="section--story__logo" loading="lazy" />
        <h2>کازین گالری؛ خانهٔ ظروف دوست‌داشتنی</h2>
        <p>
          ما در کازین گالری باور داریم آشپزخانه قلب هر خانه است؛ به همین دلیل هر ظرف، قابلمه و
          بلوری را خودمان پیش از عرضه بررسی می‌کنیم و با بسته‌بندی ضدضربه و پشتیبانی پاسخگو به
          دست شما می‌رسانیم. انتخابی مطمئن، برای خانه‌ای زیباتر.
        </p>
      </div>
    </section>
  );
}

function Home() {
  usePageMeta({ path: "/" });
  const bannersState = useAsync(() => fetchBanners(), []);
  const categoriesState = useAsync(() => getCategoryTree(), []);
  const bestSellersState = useAsync(() => listProducts({ is_best_seller: true, page_size: 4 }), []);
  const categoriesRef = useReveal();

  return (
    <div className="home">
      <HeroSlider banners={bannersState.data || []} isLoading={bannersState.isLoading} />
      <TrustStrip />

      {categoriesState.data?.length ? (
        <section className="section container reveal" ref={categoriesRef}>
          <div className="section__head">
            <h2>دسته‌بندی‌ها</h2>
            <span className="section__rule" aria-hidden="true" />
          </div>
          <div className="category-grid">
            {categoriesState.data.map((category) => (
              <Link
                key={category.id}
                to={`/shop/?category=${encodeURIComponent(category.slug)}`}
                className="category-card"
              >
                {/* Part S4 item 1: category tiles go through the shared
                    image component -- a category without an image (or with
                    a broken file) shows our logo placeholder, never an
                    empty span or a broken-image icon. */}
                <SmartImage image={category.image} alt={category.name} />
                <span className="category-card__name">{category.name}</span>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <DailyDealsSection />

      <BrandTiles />

      <ProductRow title="محصولات منتخب" params={{ is_featured: true }} />
      <ProductRow title="جدیدترین محصولات" params={{ is_new: true }} />
      <ProductRow title="پرفروش‌ترین‌ها" params={{ is_best_seller: true }} />
      {bestSellersState.data?.results?.length ? (
        <ReviewHighlights products={bestSellersState.data.results} />
      ) : null}
      <RecentlyViewed />
      <BrandStory />
    </div>
  );
}

HeroSlider.propTypes = { banners: PropTypes.arrayOf(bannerShape).isRequired, isLoading: PropTypes.bool };
TrustStrip.propTypes = {};
Countdown.propTypes = { endsAt: PropTypes.string.isRequired, serverNow: PropTypes.string.isRequired };
DailyDealsSection.propTypes = {};
ProductRow.propTypes = { title: PropTypes.string.isRequired, params: PropTypes.object.isRequired };
ReviewHighlights.propTypes = { products: PropTypes.array.isRequired };
BrandStory.propTypes = {};

export default Home;
