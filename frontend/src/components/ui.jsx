/**
 * Small shared presentational primitives used across pages. Kept in one
 * module on purpose: they're a few lines each and don't warrant separate
 * files, but DO need one consistent implementation everywhere.
 */
import PropTypes from "prop-types";

export function Spinner({ label = "در حال بارگذاری…" }) {
  return (
    <div className="spinner-wrap" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function Alert({ kind = "error", children }) {
  if (!children) return null;
  return <div className={`alert alert--${kind}`}>{children}</div>;
}

/** Normalizes an API error object (see utils/apiError) into one message. */
export function errorMessage(error) {
  if (!error) return null;
  if (typeof error === "string") return error;
  if (error.message) return error.message;
  const fieldErrors = error.fieldErrors || {};
  const firstField = Object.values(fieldErrors)[0];
  if (Array.isArray(firstField) && firstField.length) return firstField.join(" ");
  return "خطایی رخ داد. دوباره تلاش کنید.";
}

export function EmptyState({ title, children }) {
  return (
    <div className="empty-state">
      <p className="empty-state__title">{title}</p>
      {children}
    </div>
  );
}

/**
 * Part R3: friendly network/API failure state with a clear retry action --
 * a failed fetch must never render as "nothing".
 */
export function ErrorState({ message, onRetry, retryLabel = "تلاش دوباره" }) {
  return (
    <div className="empty-state empty-state--error" role="alert">
      <p className="empty-state__title">ارتباط با سرور برقرار نشد.</p>
      <p className="muted">{message || "لطفاً اتصال اینترنت خود را بررسی کنید."}</p>
      {onRetry ? (
        <button type="button" className="btn btn--primary" onClick={onRetry}>
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}
ErrorState.propTypes = { message: PropTypes.node, onRetry: PropTypes.func, retryLabel: PropTypes.string };

Spinner.propTypes = { label: PropTypes.string };
Alert.propTypes = { kind: PropTypes.oneOf(["error", "success"]), children: PropTypes.node };
EmptyState.propTypes = { title: PropTypes.string.isRequired, children: PropTypes.node };
