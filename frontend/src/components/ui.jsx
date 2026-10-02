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

Spinner.propTypes = { label: PropTypes.string };
Alert.propTypes = { kind: PropTypes.oneOf(["error", "success"]), children: PropTypes.node };
EmptyState.propTypes = { title: PropTypes.string.isRequired, children: PropTypes.node };
