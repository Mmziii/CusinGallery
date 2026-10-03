import { usePageMeta } from "../hooks/usePageMeta";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import ProductCard from "../components/ProductCard";
import { bannerShape } from "../utils/shapes";
import { Alert, Spinner } from "../components/ui";
import { fetchBanners, fetchDailyDeals } from "../services/bannersApi";
import { getCategoryTree, listProducts } from "../services/catalogApi";
import { useAsync } from "../hooks/useAsync";
import { formatPrice } from "../utils/formatPrice";
import { normalizeApiError } from "../utils/apiError";

/**
 * Homepage: banners, category shortcuts, daily deals, and the three
 * curated product rows the catalog supports (featured / new / best
 * sellers). Every section is driven by real API data and simply doesn't
 * render when there's nothing active to show -- no placeholder/fake
 * content.
 */

function BannerCarousel({ banners }) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (banners.length <= 1) return undefined;
    const timer = setInterval(() => setIndex((i) => (i + 1) % banners.length), 6000);
    return () => clearInterval(timer);
  }, [banners.length]);

  if (!banners.length) return null;
  const banner = banners[index];

  return (
    <section className="banner" aria-label="بنرهای تبلیغاتی">
      <div className="banner__slide">
        <img src={banner.image} alt={banner.title} />
        <div className="banner__overlay">
          <h2>{banner.title}</h2>
          {banner.subtitle ? <p>{banner.subtitle}</p> : null}
          {banner.cta_text && banner.cta_url ? (
            /^https?:\/\//.test(banner.cta_url) ? (
              <a className="btn btn--accent" href={banner.cta_url} target="_blank" rel="noreferrer">
                {banner.cta_text}
              </a>
            ) : (
              <Link className="btn btn--accent" to={banner.cta_url}>{banner.cta_text}</Link>
            )
          ) : null}
        </div>
      </div>
      {banners.length > 1 ? (
        <div className="banner__dots">
          {banners.map((b, i) => (
            <button
              key={b.id}
              type="button"
              className={i === index ? "dot dot--active" : "dot"}
              onClick={() => setIndex(i)}
              aria-label={`بنر ${i + 1}`}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

function Countdown({ endsAt, serverNow }) {
  const [remaining, setRemaining] = useState(null);

  useEffect(() => {
    const end = new Date(endsAt).getTime();
    const serverOffset = Date.now() - new Date(serverNow).getTime();

    const tick = () => {
      const now = Date.now() - serverOffset;
      setRemaining(Math.max(0, end - now));
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [endsAt, serverNow]);

  if (remaining === null) return null;
  if (remaining <= 0) return <span className="deal__ended">پایان یافت</span>;

  const totalSeconds = Math.floor(remaining / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (n) => String(n).padStart(2, "0");

  return (
    <span className="deal__countdown" dir="ltr">
      {pad(hours)}:{pad(minutes)}:{pad(seconds)}
    </span>
  );
}

function DailyDealsSection() {
  const { data, isLoading, error } = useAsync(() => fetchDailyDeals(), []);

  if (isLoading) return <Spinner label="در حال دریافت پیشنهادهای روز…" />;
  if (error) return null; // deals are enhancement-only; don't block the page
  if (!data?.results?.length) return null;

  return (
    <section className="section">
      <div className="section__head">
        <h2>پیشنهاد امروز</h2>
      </div>
      <div className="deals-grid">
        {data.results.map((deal) => (
          <Link key={deal.id} to={`/products/${deal.product.slug}/`} className="deal-card">
            {deal.product.primary_image?.image ? (
              <img src={deal.product.primary_image.image} alt={deal.product.name} loading="lazy" />
            ) : null}
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
    </section>
  );
}

function ProductRow({ title, params }) {
  const { data, isLoading, error } = useAsync(() => listProducts(params), [JSON.stringify(params)]);

  if (isLoading) return <Spinner />;
  if (error) return <Alert>{normalizeApiError(error).message}</Alert>;
  if (!data?.results?.length) return null;

  return (
    <section className="section">
      <div className="section__head">
        <h2>{title}</h2>
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

function Home() {
  usePageMeta({ path: "/" });
  const bannersState = useAsync(() => fetchBanners(), []);
  const categoriesState = useAsync(() => getCategoryTree(), []);

  return (
    <div className="home">
      <BannerCarousel banners={bannersState.data || []} />

      {categoriesState.data?.length ? (
        <section className="section">
          <div className="section__head">
            <h2>دسته‌بندی‌ها</h2>
          </div>
          <div className="category-grid">
            {categoriesState.data.map((category) => (
              <Link
                key={category.id}
                to={`/shop/?category=${encodeURIComponent(category.slug)}`}
                className="category-card"
              >
                {category.image ? <img src={category.image} alt={category.name} loading="lazy" /> : null}
                <span>{category.name}</span>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <DailyDealsSection />

      <ProductRow title="محصولات منتخب" params={{ is_featured: true }} />
      <ProductRow title="جدیدترین محصولات" params={{ is_new: true }} />
      <ProductRow title="پرفروش‌ترین‌ها" params={{ is_best_seller: true }} />
    </div>
  );
}

BannerCarousel.propTypes = { banners: PropTypes.arrayOf(bannerShape).isRequired };
Countdown.propTypes = { endsAt: PropTypes.string.isRequired, serverNow: PropTypes.string.isRequired };
ProductRow.propTypes = { title: PropTypes.string.isRequired, params: PropTypes.object.isRequired };

export default Home;
