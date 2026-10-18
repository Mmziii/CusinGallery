import PropTypes from "prop-types";
import { useParams } from "react-router-dom";

import { ContentSkeleton } from "../components/Skeletons";
import { ErrorState, errorMessage } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { usePageMeta } from "../hooks/usePageMeta";
import { getBrand } from "../services/catalogApi";
import { normalizeApiError } from "../utils/apiError";
import NotFound from "./NotFound";
import ShopPage from "./ShopPage";

function BrandStatus({ error, onRetry }) {
  usePageMeta({ title: error ? "صفحه یافت نشد" : "محصولات برند", noindex: true });
  if (error?.response?.status === 404) return <NotFound />;
  if (error) return <ErrorState message={errorMessage(normalizeApiError(error))} onRetry={onRetry} />;
  return <ContentSkeleton label="در حال دریافت برند…" />;
}

/** A real brand detail lookup prevents empty listings from hiding a 404. */
function BrandPage() {
  const { slug } = useParams();
  const state = useAsync(() => getBrand(slug), [slug]);
  if (state.error || !state.data || state.data.slug !== slug) {
    return <BrandStatus error={state.error} onRetry={state.refetch} />;
  }
  return <ShopPage key={slug} brand={state.data} />;
}

BrandStatus.propTypes = { error: PropTypes.object, onRetry: PropTypes.func.isRequired };

export default BrandPage;
