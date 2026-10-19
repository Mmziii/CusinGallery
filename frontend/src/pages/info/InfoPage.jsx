import PropTypes from "prop-types";
import { Link } from "react-router-dom";

import { ErrorState } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import { usePageMeta } from "../../hooks/usePageMeta";
import { fetchInfoPage } from "../../services/siteApi";
import { normalizeApiError } from "../../utils/apiError";
import NotFound from "../NotFound";

/**
 * One owner-editable info page (Task 3): about, contact, shipping &
 * returns, terms, privacy.
 *
 * The text lives in the database now, so the page renders the `body` HTML
 * the backend sanitised with an explicit allowlist (apps/core/sanitize.py)
 * -- never a raw admin field. SEO title/description come from the same
 * response.
 *
 * An unpublished page makes /api/v1/site/pages/<slug>/ answer 404; this
 * component then renders the storefront's own 404 view. Django already
 * answered that URL with HTTP 404 + noindex (apps/core/spa.py), so both
 * the crawler and the shopper see an honest "not found".
 */

const FALLBACK_TITLES = {
  about: "دربارهٔ ما",
  contact: "تماس با ما",
  "shipping-returns": "ارسال و مرجوعی",
  terms: "قوانین و مقررات",
  privacy: "حریم خصوصی",
};

function InfoPageArticle({ page, path }) {
  usePageMeta({
    title: page.seo_title || page.title,
    description: page.seo_description,
    path,
  });

  return (
    <article className="container info-page">
      <h1>{page.title}</h1>
      <div
        className="info-page__body card rich-text"
        // Sanitised twice on the server (on save and when served) with the
        // allowlist in apps/core/sanitize.py: no <script>, <style>, on*
        // attributes or javascript: URLs can reach this string.
        // eslint-disable-next-line react/no-danger
        dangerouslySetInnerHTML={{ __html: page.body || "" }}
      />
    </article>
  );
}

function InfoPageSkeleton({ title }) {
  return (
    <div className="container info-page" aria-busy="true">
      <h1>{title}</h1>
      <div className="info-page__body card">
        <div className="skeleton-line" />
        <div className="skeleton-line" />
        <div className="skeleton-line skeleton-line--short" />
      </div>
    </div>
  );
}

function InfoPage({ slug, path }) {
  const { data, isLoading, error, refetch } = useAsync(() => fetchInfoPage(slug), [slug]);
  const title = FALLBACK_TITLES[slug] || "اطلاعات فروشگاه";

  if (isLoading) return <InfoPageSkeleton title={title} />;

  // A network/server failure is retryable; a 404 is an answer, not an error.
  if (error) {
    return (
      <div className="container info-page">
        <h1>{title}</h1>
        <ErrorState message={normalizeApiError(error).message} onRetry={refetch} />
        <p>
          <Link to="/">بازگشت به فروشگاه</Link>
        </p>
      </div>
    );
  }

  if (!data) return <NotFound />;
  return <InfoPageArticle page={data} path={path} />;
}

InfoPage.propTypes = {
  slug: PropTypes.oneOf(Object.keys(FALLBACK_TITLES)).isRequired,
  path: PropTypes.string.isRequired,
};

InfoPageArticle.propTypes = {
  page: PropTypes.shape({
    title: PropTypes.string.isRequired,
    body: PropTypes.string,
    seo_title: PropTypes.string,
    seo_description: PropTypes.string,
  }).isRequired,
  path: PropTypes.string.isRequired,
};

InfoPageSkeleton.propTypes = { title: PropTypes.string.isRequired };

export default InfoPage;
