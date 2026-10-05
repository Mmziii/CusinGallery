import { Link } from "react-router-dom";

import StarRating from "../../components/StarRating";
import { EmptyState, ErrorState, Spinner, errorMessage } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";
import * as reviewsApi from "../../services/reviewsApi";

const STATUS_LABELS = {
  pending: "در انتظار تأیید",
  approved: "تأیید شده",
  rejected: "رد شده",
};

function ReviewsPage() {
  const { data, isLoading, error, refetch } = useAsync(() => reviewsApi.fetchMyReviews(), []);

  if (isLoading) return <Spinner label="در حال دریافت نظرات…" />;
  if (error) return <ErrorState message={errorMessage(error)} onRetry={refetch} />;

  const reviews = data?.results || [];
  if (!reviews.length) {
    return (
      <EmptyState title="هنوز نظری ثبت نکرده‌اید.">
        <Link className="btn btn--primary" to="/shop/">مشاهده فروشگاه</Link>
      </EmptyState>
    );
  }

  const handleDelete = async (id) => {
    await reviewsApi.deleteReview(id);
    refetch();
  };

  return (
    <div className="my-reviews">
      <h1>نظرات من</h1>
      <div className="review-list">
        {reviews.map((review) => (
          <article key={review.id} className="review review--own">
            <header>
              <Link to={`/products/${review.product_slug}/`}>{review.product_name}</Link>
              <span className={`tag tag--review-${review.status}`}>
                {STATUS_LABELS[review.status] || review.status}
              </span>
              <StarRating rating={review.rating} />
            </header>
            {review.title ? <h4>{review.title}</h4> : null}
            {review.body ? <p>{review.body}</p> : null}
            <div className="review__actions">
              <time className="muted">{new Date(review.created_at).toLocaleDateString("fa-IR")}</time>
              <button type="button" className="link-danger" onClick={() => handleDelete(review.id)}>
                حذف
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

export default ReviewsPage;
