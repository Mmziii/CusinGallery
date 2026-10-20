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

/** One full rotation of the desktop coverflow (ms) -- matches the CSS. */
const DEALS_ROTATE_MS = 600;

/** The furthest-offset card still shown on each side of the centre one. */
const DEALS_MAX_SIDE = 2;

/**
 * Circular distance from the centre card to `index`, signed like the layout:
 * positive = the NEXT deal (drawn on the LEFT in this RTL page), negative =
 * the PREVIOUS one (drawn on the RIGHT). With 2 deals the second one reports
 * +1, i.e. exactly one card on the side; with an even count the shortest way
 * round is chosen so no card ever appears twice.
 */
function coverflowOffset(index, centre, count) {
  if (count <= 1) return 0;
  let offset = ((index - centre) % count + count) % count;
  if (offset > count / 2) offset -= count;
  return offset;
}

/**
 * The card CONTENT (image, badge, name, prices, countdown, CTA) -- shared by
 * every coverflow card so a card moving to the centre never has to remount
 * its content (which is what makes the motion continuous instead of a swap).
 */
function DealCardBody({ deal, discount, serverNow }) {
  const originalPrice = getDealOriginalPrice(deal);
  return (
    <>
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
    </>
  );
}

DealCardBody.propTypes = {
  deal: PropTypes.object.isRequired,
  discount: PropTypes.number,
  serverNow: PropTypes.string.isRequired,
};

/**
 * One desktop coverflow card.
 *
 * The wrapper is the ONLY thing that moves: it is absolutely positioned in
 * the fixed-height stage and its transform/opacity/blur come from CSS
 * variables, so going from a side slot to the centre (or back) is one
 * continuous 600ms ease-in-out interpolation -- no remount, no jump.
 * A side card is exposed as a button (it rotates the carousel, it does NOT
 * navigate); only the centre card is the real product link.
 */
function CoverflowCard({ deal, offset, serverNow, onSelect }) {
  const distance = Math.abs(offset);
  const isCentre = offset === 0;
  const isNear = distance === 2;
  const isHidden = distance > DEALS_MAX_SIDE;
  // Positive offsets (the next deal) sit on the LEFT in RTL, negative (the
  // previous deal) on the RIGHT -- a physical transition value, so the sign
  // is deliberately not logical.
  const dx = offset === 0 ? 0 : -Math.sign(offset) * (distance === 1 ? 55 : 92);
  const scale = isCentre ? 1 : distance === 1 ? 0.8 : isNear ? 0.62 : 0.5;
  const opacity = isCentre ? 1 : distance === 1 ? 0.45 : isNear ? 0.25 : 0;
  const blur = isCentre ? 0 : distance === 1 ? 1.5 : 2.5;
  const discount = dealDiscount(getDealOriginalPrice(deal), deal.sale_price);

  return (
    <div
      className={[
        "deals-cf__card",
        isCentre ? "is-centre" : "is-side",
        offset > 0 ? "is-next" : offset < 0 ? "is-prev" : "",
        isNear ? "is-near" : "",
        isHidden ? "is-hidden" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-offset={offset}
      data-role={isCentre ? "centre" : "side"}
      aria-hidden={isHidden ? "true" : undefined}
      style={{
        "--cf-dx": dx,
        "--cf-scale": scale,
        "--cf-opacity": opacity,
        "--cf-blur": `${blur}px`,
        zIndex: 10 - distance * 2,
      }}
    >
      <Link
        to={`/products/${deal.product.slug}/`}
        className="deal-card"
        role={isCentre ? undefined : "button"}
        aria-label={isCentre ? undefined : `نمایش پیشنهاد ${faDigits(deal.product.name)}`}
        tabIndex={isHidden ? -1 : undefined}
        onClick={
          isCentre
            ? undefined
            : (event) => {
                // A side card only brings itself to the centre.
                event.preventDefault();
                onSelect();
              }
        }
      >
        <DealCardBody deal={deal} discount={discount} serverNow={serverNow} />
      </Link>
    </div>
  );
}

CoverflowCard.propTypes = {
  deal: PropTypes.object.isRequired,
  offset: PropTypes.number.isRequired,
  serverNow: PropTypes.string.isRequired,
  onSelect: PropTypes.func.isRequired,
};

function DailyDealsSection({ title }) {
  const ref = useReveal();
  const { data, isLoading, error } = useAsync(() => fetchDailyDeals(), []);
  const isMobile = useMediaQuery("(max-width: 767px)");
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

  const [currentIndex, setCurrentIndex] = useState(0);
  // True for the duration of one coverflow rotation: the stage's CSS uses it
  // to fade the incoming centre card's text in AFTER it has arrived.
  const [rotating, setRotating] = useState(false);
  const rotateTimer = useRef(null);
  const [isPaused, setIsPaused] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [tabHidden, setTabHidden] = useState(() =>
    typeof document !== "undefined" ? document.visibilityState === "hidden" : false
  );

  // Reactive clock to expire deals without reload
  const [, setTick] = useState(0);
  const baseServerTime = useRef(null);
  const baseClientTime = useRef(Date.now());
  // Mirrors currentIndex for the event handlers below, so a step can be
  // decided synchronously (two clicks in one frame must not both start from
  // the same index).
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
   * The ONE way the set rotates -- side cards, arrows, keyboard and the
   * auto-advance timer all come through here, so every change (including
   * the automatic one) plays the same continuous motion: each card is
   * re-slotted and its own CSS transition carries it to the new place.
   * Under prefers-reduced-motion the swap is instant.
   */
  const showDeal = useCallback((next) => {
    const previous = shownIndexRef.current;
    if (next === previous) return;
    shownIndexRef.current = next;
    setCurrentIndex(next);
    if (reducedMotion) {
      setRotating(false);
      return;
    }
    setRotating(true);
    if (rotateTimer.current) clearTimeout(rotateTimer.current);
    rotateTimer.current = setTimeout(() => setRotating(false), DEALS_ROTATE_MS);
  }, [reducedMotion]);

  useEffect(() => () => {
    if (rotateTimer.current) clearTimeout(rotateTimer.current);
  }, []);

  // 10s auto-advance (pause on hover/focus/hidden tab/reduced-motion and
  // whenever there is nothing to advance to).
  useEffect(() => {
    if (activeCount <= 1 || isPaused || isFocused || tabHidden || reducedMotion || isMobile) {
      return undefined;
    }
    const timer = setInterval(() => {
      showDeal((shownIndexRef.current + 1) % activeCount);
    }, 10000);
    return () => clearInterval(timer);
  }, [activeCount, isPaused, isFocused, tabHidden, reducedMotion, isMobile, showDeal]);

  if (isLoading) return null;
  if (error || !data?.results?.length) return null;
  if (activeDeals.length === 0) return null;

  const safeIndex = Math.min(currentIndex, activeDeals.length - 1);
  // A deal can expire between ticks and shrink the set under the cursor;
  // clamp the ref too so the next arrow/keyboard step does not skip.
  if (shownIndexRef.current !== safeIndex) shownIndexRef.current = safeIndex;
  const currentDeal = activeDeals[safeIndex] || activeDeals[0];

  const goPrev = () => showDeal((shownIndexRef.current - 1 + activeDeals.length) % activeDeals.length);
  const goNext = () => showDeal((shownIndexRef.current + 1) % activeDeals.length);
  // Arrow keys follow the visual sides in RTL: ArrowLeft takes the card on
  // the left (the next deal) to the centre, ArrowRight the previous one.
  const onStageKeyDown = (event) => {
    if (activeCount <= 1) return;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      goNext();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      goPrev();
    }
  };

  const nearestExpiry = activeDeals.reduce((min, deal) => {
    return !min || new Date(deal.ends_at) < new Date(min) ? deal.ends_at : min;
  }, null);

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
          /* Desktop (>=1024px) coverflow: the current deal is the large
             card in the middle, the previous/next deals sit behind it on
             the right/left, smaller, dimmed and softly blurred; two more
             stack further out on each side. Picking a side card (or an
             arrow, or ArrowLeft/ArrowRight) rotates the whole set with one
             continuous ~600ms CSS transform -- nothing is re-mounted. */
          <div
            className="deals-desktop"
            onMouseEnter={() => setIsPaused(true)}
            onMouseLeave={() => setIsPaused(false)}
            onFocus={() => setIsFocused(true)}
            onBlur={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget)) setIsFocused(false);
            }}
            onKeyDown={onStageKeyDown}
          >
            <div
              className="deals-cf"
              role="group"
              aria-roledescription="carousel"
              aria-label={title}
            >
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

              <div
                className={`deals-cf__stage${rotating ? " is-rotating" : ""}`}
                data-count={activeDeals.length}
              >
                {activeDeals.map((deal, idx) => {
                  const offset = coverflowOffset(idx, safeIndex, activeDeals.length);
                  return (
                    <CoverflowCard
                      key={deal.id}
                      deal={deal}
                      offset={offset}
                      serverNow={data.server_now}
                      onSelect={() => showDeal(idx)}
                    />
                  );
                })}
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

              {/* Screen readers hear the centre card change. */}
              <p className="sr-only" aria-live="polite">
                {`پیشنهاد ${faDigits(safeIndex + 1)} از ${faDigits(activeDeals.length)}: ${faDigits(currentDeal.product.name)}`}
              </p>
            </div>
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
