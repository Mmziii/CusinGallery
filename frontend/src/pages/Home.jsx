import { faDigits } from "../utils/faDigits";
import PropTypes from "prop-types";
import { useCallback, useEffect, useRef, useState } from "react";
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
import useSiteContent from "../hooks/useSiteContent";
import useReveal from "../hooks/useReveal";
import { useAsync } from "../hooks/useAsync";
import { bannerShape } from "../utils/shapes";
import { normalizeApiError } from "../utils/apiError";
import { formatPrice } from "../utils/formatPrice";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { fetchBanners, fetchDailyDeals } from "../services/bannersApi";
import { getCategoryTree, listProducts } from "../services/catalogApi";
import { mainGroups } from "../utils/categories";
import { fetchProductReviews } from "../services/reviewsApi";

/**
 * Homepage (Part 3 redesign): full-width hero slider fed by the banners
 * admin, trust strip, category tiles, daily-deal feature block with
 * countdown, curated rows, a short brand story and review highlights.
 * Everything stays API-driven and silently skips absent sections.
 */
function HeroCopy({ hero }) {
  if (!hero?.title && !hero?.subtitle) return null;
  return (
    <section className="hero hero--copy" aria-label="معرفی فروشگاه">
      <div className="hero__copy container">
        {hero.title ? <h2>{hero.title}</h2> : null}
        {hero.subtitle ? <p>{hero.subtitle}</p> : null}
        {hero.button_text ? (
          <Link className="btn btn--gold" to={hero.button_link || "/shop/"}>
            {hero.button_text}
          </Link>
        ) : null}
      </div>
    </section>
  );
}

function HeroSlider({ banners, isLoading, hero }) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const touchX = useRef(null);

  useEffect(() => {
    if (paused || banners.length <= 1) return undefined;
    const timer = setInterval(() => setIndex((i) => (i + 1) % banners.length), 6000);
    return () => clearInterval(timer);
  }, [paused, banners.length]);

  if (isLoading) return <HeroSkeleton />;
  // Owner-written hero copy (Task 3) is the homepage hero until at least
  // one banner exists; the banner admin then owns the slider copy.
  if (banners.length === 0) return <HeroCopy hero={hero} />;

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
                <h2>{banner.title}</h2>
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

const TRUST_ITEMS = [
  { icon: "shield-check", label: "تضمین اصالت کالا و سلامت فیزیکی اجناس" },
  { icon: "box", label: "بسته‌بندی ضدضربهٔ کالا" },
  { icon: "truck", label: "ارسال به سراسر ایران" },
  { icon: "lock", label: "پرداخت امن اینترنتی" },
  { icon: "bolt-fast", label: "امکان تحویل اکسپرس" },
];

function TrustStrip({ items }) {
  const ref = useReveal();
  return (
    <section className="trust-strip reveal" ref={ref} aria-label="مزایای خرید">
      <div className="container trust-strip__inner">
        {items.map(({ icon, label }) => (
          <div key={label} className="trust-strip__item">
            <Icon name={icon} size={20} />
            <span>{label}</span>
          </div>
        ))}
      </div>
    </section>
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
  const padFa = (n) => faDigits(String(n).padStart(2, "0"));
  return (
    <span className="countdown" role="timer" aria-label="زمان باقی‌مانده">
      <span className="countdown__segment">
        <span className="countdown__value">{padFa(hours)}</span>
        <span className="countdown__label">ساعت</span>
      </span>
      <span className="countdown__sep" aria-hidden="true">:</span>
      <span className="countdown__segment">
        <span className="countdown__value">{padFa(minutes)}</span>
        <span className="countdown__label">دقیقه</span>
      </span>
      <span className="countdown__sep" aria-hidden="true">:</span>
      <span className="countdown__segment">
        <span className="countdown__value">{padFa(seconds)}</span>
        <span className="countdown__label">ثانیه</span>
      </span>
    </span>
  );
}

function getDealOriginalPrice(deal) {
  const pInfo = deal?.product?.price_info;
  const compareAt = pInfo?.compare_at_price != null ? Number(pInfo.compare_at_price) : null;
  if (compareAt && compareAt > 0) return compareAt;
  const regular = deal?.product?.regular_price != null ? Number(deal.product.regular_price) : null;
  if (regular && regular > 0) return regular;
  const pInfoPrice = pInfo?.price != null ? Number(pInfo.price) : null;
  if (pInfoPrice && pInfoPrice > deal.sale_price) return pInfoPrice;
  const prodPrice = deal?.product?.price != null ? Number(deal.product.price) : null;
  if (prodPrice && prodPrice > deal.sale_price) return prodPrice;
  return null;
}

/**
 * Discount badge for a deal: FLOORED, and never 100%. Rounding 99.98% up
 * to «۱۰۰٪» promises more than the price actually gives, and a 0-rial deal
 * price would round to a perfect hundred -- neither may reach the badge.
 */
function dealDiscount(originalPrice, salePrice) {
  if (!(originalPrice > 0) || !(originalPrice > salePrice)) return 0;
  return Math.min(99, Math.floor(((originalPrice - salePrice) / originalPrice) * 100));
}

/** How long a slide change takes (ms) -- must match the CSS animation. */
const DEALS_TRANSITION_MS = 450;

function DealCard({ deal, discount, serverNow }) {
  const originalPrice = getDealOriginalPrice(deal);
  return (
    <Link to={`/products/${deal.product.slug}/`} className="deal-card">
      <div className="deal-card__media">
        <SmartImage image={deal.product.primary_image || null} alt={faDigits(deal.product.name)} />
        {discount > 0 ? (
          <span className="deal-card__badge">{faDigits(discount)}٪ تخفیف</span>
        ) : null}
      </div>
      <div className="deal-card__body">
        <div className="deal-card__name">{faDigits(deal.product.name)}</div>
        <div className="deal-card__prices">
          <span className="deal-card__sale">{formatPrice(deal.sale_price)} تومان</span>
          {originalPrice && originalPrice > deal.sale_price ? (
            <s className="deal-card__regular">{formatPrice(originalPrice)} تومان</s>
          ) : null}
        </div>
        <Countdown endsAt={deal.ends_at} serverNow={serverNow} />
        <span className="deal-card__cta">مشاهده محصول</span>
      </div>
    </Link>
  );
}

DealCard.propTypes = {
  deal: PropTypes.object.isRequired,
  discount: PropTypes.number,
  serverNow: PropTypes.string.isRequired,
};

function DailyDealsSection({ title }) {
  const ref = useReveal();
  const { data, isLoading, error } = useAsync(() => fetchDailyDeals(), []);
  const isMobile = useMediaQuery("(max-width: 767px)");
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

  const [currentIndex, setCurrentIndex] = useState(0);
  // The slide that is still fading OUT while the new one fades in (null
  // when nothing is moving -- which is also the permanent state under
  // prefers-reduced-motion).
  const [outgoingIndex, setOutgoingIndex] = useState(null);
  // Travel direction of the last change: 1 = forward (the new slide comes
  // in from the right, the old one leaves to the left), -1 = backwards.
  const [direction, setDirection] = useState(1);
  const [isPaused, setIsPaused] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [tabHidden, setTabHidden] = useState(() =>
    typeof document !== "undefined" ? document.visibilityState === "hidden" : false
  );

  // Reactive clock to expire deals without reload
  const [, setTick] = useState(0);
  const baseServerTime = useRef(null);
  const baseClientTime = useRef(Date.now());
  // Mirrors currentIndex for the event handlers below, so a change can be
  // decided (and the outgoing slide captured) outside a state updater.
  const shownIndexRef = useRef(0);

  if (data?.server_now && baseServerTime.current === null) {
    baseServerTime.current = new Date(data.server_now).getTime();
    baseClientTime.current = Date.now();
  }

  useEffect(() => {
    const timer = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  // Hidden tab detection
  useEffect(() => {
    const onVisibilityChange = () => {
      setTabHidden(document.visibilityState === "hidden");
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, []);

  const currentTimestamp = baseServerTime.current !== null
    ? baseServerTime.current + (Date.now() - baseClientTime.current)
    : Date.now();

  // Filter out expired deals so they disappear on expiry without reload
  const activeDeals = (data?.results || []).filter((deal) => {
    const ends = new Date(deal.ends_at).getTime();
    return ends > currentTimestamp;
  });

  const activeCount = activeDeals.length;

  /**
   * The ONE way the slide changes -- arrows, thumbnails and the
   * auto-advance timer all come through here, so every change (including
   * the automatic one) plays the same cross-fade + slide animation.
   * Under prefers-reduced-motion the swap is instant.
   */
  const showDeal = useCallback((next, travel) => {
    const previous = shownIndexRef.current;
    if (next === previous) return;
    shownIndexRef.current = next;
    if (reducedMotion) {
      setOutgoingIndex(null);
    } else {
      setDirection(travel);
      setOutgoingIndex(previous);
    }
    setCurrentIndex(next);
  }, [reducedMotion]);

  // 10s auto-advance (pause on hover/focus/hidden tab/reduced-motion)
  useEffect(() => {
    if (activeCount <= 1 || isPaused || isFocused || tabHidden || reducedMotion || isMobile) {
      return undefined;
    }
    const timer = setInterval(() => {
      showDeal((shownIndexRef.current + 1) % activeCount, 1);
    }, 10000);
    return () => clearInterval(timer);
  }, [activeCount, isPaused, isFocused, tabHidden, reducedMotion, isMobile, showDeal]);

  // Drop the outgoing slide once its fade-out has played.
  useEffect(() => {
    if (outgoingIndex === null) return undefined;
    const timer = setTimeout(() => setOutgoingIndex(null), DEALS_TRANSITION_MS);
    return () => clearTimeout(timer);
  }, [outgoingIndex]);

  if (isLoading) return null;
  if (error || !data?.results?.length) return null;
  if (activeDeals.length === 0) return null;

  const safeIndex = Math.min(currentIndex, activeDeals.length - 1);
  const currentDeal = activeDeals[safeIndex] || activeDeals[0];
  const outgoingDeal = outgoingIndex === null ? null : activeDeals[outgoingIndex];

  const goPrev = () => showDeal((shownIndexRef.current - 1 + activeDeals.length) % activeDeals.length, -1);
  const goNext = () => showDeal((shownIndexRef.current + 1) % activeDeals.length, 1);

  const nearestExpiry = activeDeals.reduce((min, deal) => {
    return !min || new Date(deal.ends_at) < new Date(min) ? deal.ends_at : min;
  }, null);

  const originalPrice = getDealOriginalPrice(currentDeal);
  const discount = dealDiscount(originalPrice, currentDeal.sale_price);

  return (
    <section className="section section--dark reveal" ref={ref} aria-label={title}>
      <div className="container">
        <div className="section__head">
          <h2>{title}</h2>
          <span className="section__rule" aria-hidden="true" />
        </div>

        {isMobile ? (
          /* Phone full-width colored band with shared countdown + swipeable compact deal cards with scroll-snap */
          <div className="deals-mobile">
            <div className="deals-mobile__header">
              <div className="deals-mobile__head-main">
                <span className="deals-mobile__title">{title}</span>
                {/* «مشاهده همه» lands on the shop's discounted-products
                    filter. `on_sale=true` is the value the API documents
                    (1/yes also work, but the link should not rely on the
                    tolerant parser). */}
                <Link className="deals-mobile__all" to="/shop/?on_sale=true">
                  مشاهده همه
                </Link>
              </div>
              <Countdown endsAt={nearestExpiry} serverNow={data.server_now} />
            </div>
            <div className="deals-mobile__track" role="region" aria-label="پیشنهادهای روز">
              {activeDeals.map((deal) => {
                const orig = getDealOriginalPrice(deal);
                const disc = dealDiscount(orig, deal.sale_price);
                return (
                  <Link
                    key={deal.id}
                    to={`/products/${deal.product.slug}/`}
                    className="deals-mobile__card"
                  >
                    <div className="deals-mobile__media">
                      <SmartImage image={deal.product.primary_image || null} alt={faDigits(deal.product.name)} />
                      {disc > 0 ? (
                        <span className="deal-card__badge">{faDigits(disc)}٪ تخفیف</span>
                      ) : null}
                    </div>
                    <div className="deals-mobile__body">
                      <div className="deal-card__name deals-mobile__name">{faDigits(deal.product.name)}</div>
                      <div className="deal-card__prices deals-mobile__prices">
                        <span className="deal-card__sale">{formatPrice(deal.sale_price)} تومان</span>
                        {orig && orig > deal.sale_price ? (
                          <s className="deal-card__regular">{formatPrice(orig)} تومان</s>
                        ) : null}
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        ) : (
          /* Desktop smaller main slide (40-45% width) + prev/next round arrow buttons + thumbnail row (5-6 visible) */
          <div
            className="deals-desktop"
            onMouseEnter={() => setIsPaused(true)}
            onMouseLeave={() => setIsPaused(false)}
            onFocus={() => setIsFocused(true)}
            onBlur={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget)) setIsFocused(false);
            }}
          >
            <div className="deals-stage">
              {activeDeals.length > 1 ? (
                <button
                  type="button"
                  className="deals-arrow deals-arrow--prev"
                  aria-label="پیشنهاد قبلی"
                  onClick={goPrev}
                >
                  <Icon name="chevron-right" size={20} />
                </button>
              ) : null}

              {/* Both slides live in the SAME grid cell, so the box height is
                  the taller of the two and nothing jumps while they cross
                  over; the outgoing one is dropped when its fade ends. */}
              <div
                className="deals-grid deals-stage__card deals-slides"
                style={{ "--deals-dir": direction }}
              >
                {outgoingDeal ? (
                  <div
                    className="deals-slide deals-slide--out"
                    key={`out-${outgoingDeal.id}`}
                    aria-hidden="true"
                  >
                    <DealCard
                      deal={outgoingDeal}
                      discount={dealDiscount(getDealOriginalPrice(outgoingDeal), outgoingDeal.sale_price)}
                      serverNow={data.server_now}
                    />
                  </div>
                ) : null}
                <div
                  className={`deals-slide${outgoingDeal ? " deals-slide--in" : ""}`}
                  key={`in-${currentDeal.id}`}
                >
                  <DealCard
                    deal={currentDeal}
                    discount={discount}
                    serverNow={data.server_now}
                  />
                </div>
              </div>

              {activeDeals.length > 1 ? (
                <button
                  type="button"
                  className="deals-arrow deals-arrow--next"
                  aria-label="پیشنهاد بعدی"
                  onClick={goNext}
                >
                  <Icon name="chevron-left" size={20} />
                </button>
              ) : null}
            </div>

            {/* Thumbnail row (5-6 visible) */}
            {activeDeals.length > 1 ? (
              <div
                className="deals-thumbs"
                role="tablist"
                aria-label="انتخاب پیشنهاد"
                style={{ "--deals-thumb-index": safeIndex }}
              >
                <div className="deals-thumbs__track">
                  {activeDeals.map((deal, idx) => (
                    <button
                      key={deal.id}
                      type="button"
                      role="tab"
                      aria-selected={idx === safeIndex}
                      className="deals-thumb"
                      onClick={() => showDeal(idx, idx > safeIndex ? 1 : -1)}
                      aria-label={faDigits(deal.product.name)}
                    >
                      <SmartImage image={deal.product.primary_image || null} alt="" />
                    </button>
                  ))}
                  {/* The highlight is one box that SLIDES to the selected
                      thumb instead of fading in per thumbnail. */}
                  <span className="deals-thumbs__highlight" aria-hidden="true" />
                </div>
              </div>
            ) : null}
          </div>
        )}
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

function ReviewHighlights({ products, title }) {
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
        <h2>{title}</h2>
        <span className="section__rule" aria-hidden="true" />
      </div>
      <div className="review-highlights">
        {data.map(({ product, review }) => (
          <blockquote key={product.id} className="review-highlight">
            <p>«{review.body || review.title}»</p>
            <footer>
              {review.rating ? <StarRating rating={faDigits(review.rating)} /> : null}
              <cite>خریدارِ {faDigits(product.name)}</cite>
            </footer>
          </blockquote>
        ))}
      </div>
    </section>
  );
}

function BrandStory({ story }) {
  const ref = useReveal();
  return (
    <section className="section section--story reveal" ref={ref}>
      <div className="container section--story__inner">
        <img src="/brand/lockup.svg" alt="CusinGallery" className="section--story__logo" loading="lazy" />
        {story.title ? <h2>{story.title}</h2> : null}
        {story.text ? <p>{story.text}</p> : null}
      </div>
    </section>
  );
}

function Home() {
  usePageMeta({ path: "/" });
  const content = useSiteContent();
  const homeCopy = content.home || {};
  const sections = homeCopy.sections || {};
  const hero = homeCopy.hero || {};
  // An empty owner list means "hide the strip" (a real payload is the only
  // way to get []); a failed request yields the default payload instead.
  const trustItems = content.trust_strip || TRUST_ITEMS;
  const bannersState = useAsync(() => fetchBanners(), []);
  const categoriesState = useAsync(() => getCategoryTree(), []);
  const bestSellersState = useAsync(() => listProducts({ is_best_seller: true, page_size: 4 }), []);
  const categoriesRef = useReveal();
  // Stage 1: the tiles show the main groups (children of
  // the «آشپزخانه» root), never the root itself.
  const categoryGroups = mainGroups(categoriesState.data || []);

  return (
    <div className="home">
      <h1 className="sr-only">{homeCopy.heading || "کازین گالری؛ فروشگاه لوازم خانه و آشپزخانه"}</h1>
      <HeroSlider
        banners={bannersState.data || []}
        isLoading={bannersState.isLoading}
        hero={hero}
      />
      <TrustStrip items={trustItems} />

      {categoryGroups.length ? (
        <section className="section container reveal" ref={categoriesRef}>
          <div className="section__head">
            <h2>{sections.categories || "دسته‌بندی‌ها"}</h2>
            <span className="section__rule" aria-hidden="true" />
          </div>
          <div className="category-grid">
            {categoryGroups.map((category) => (
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

      <DailyDealsSection title={sections.deals || "پیشنهاد امروز"} />

      <BrandTiles />

      <ProductRow title={sections.featured || "محصولات منتخب"} params={{ is_featured: true }} />
      <ProductRow title={sections.new || "جدیدترین محصولات"} params={{ is_new: true }} />
      <ProductRow title={sections.best_sellers || "پرفروش‌ترین‌ها"} params={{ is_best_seller: true }} />
      {bestSellersState.data?.results?.length ? (
        <ReviewHighlights
          products={bestSellersState.data.results}
          title={sections.reviews || "از زبان خریداران"}
        />
      ) : null}
      <RecentlyViewed />
      <BrandStory story={homeCopy.story || {}} />
    </div>
  );
}

HeroSlider.propTypes = {
  banners: PropTypes.arrayOf(bannerShape).isRequired,
  isLoading: PropTypes.bool,
  hero: PropTypes.object,
};
HeroCopy.propTypes = { hero: PropTypes.object };
TrustStrip.propTypes = { items: PropTypes.arrayOf(PropTypes.object).isRequired };
Countdown.propTypes = { endsAt: PropTypes.string.isRequired, serverNow: PropTypes.string.isRequired };
DailyDealsSection.propTypes = { title: PropTypes.string.isRequired };
ProductRow.propTypes = { title: PropTypes.string.isRequired, params: PropTypes.object.isRequired };
ReviewHighlights.propTypes = { products: PropTypes.array.isRequired, title: PropTypes.string.isRequired };
BrandStory.propTypes = { story: PropTypes.object.isRequired };

export default Home;
