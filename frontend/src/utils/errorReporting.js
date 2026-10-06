import apiClient from "../services/apiClient";

/**
 * Part S3 item 9: frontend error reporting WITHOUT a Sentry SDK.
 *
 * The storefront deliberately ships no @sentry/browser (heavy dependency,
 * slow Iranian network): when an error is caught, a tiny report is POSTed
 * to the backend's capture endpoint (apps/core/views.py,
 * ReportFrontendErrorView), which forwards it into the EXISTING Sentry
 * setup (backend SENTRY_DSN + sentry_sdk).
 *
 * Double gate -- data only leaves the browser when BOTH are open:
 *   - build-time VITE_SENTRY_DSN is non-empty (this file), AND
 *   - the backend's own SENTRY_DSN is configured (server-side capture);
 *     without it the report is only written to the server log.
 * VITE_SENTRY_DSN empty => reportFrontendError is a no-op that never
 * sends anything.
 */
const ENABLED = Boolean(import.meta.env.VITE_SENTRY_DSN);

export function isReportingEnabled() {
  return ENABLED;
}

export function reportFrontendError({ message, component = null, stack = null }) {
  if (!ENABLED) return; // off = zero network activity
  try {
    // Fire-and-forget; error reporting must never throw or block the UI.
    apiClient
      .post("/site/report-error/", {
        message: String(message || "unknown error").slice(0, 2000),
        component: component ? String(component).slice(0, 200) : null,
        url: typeof window !== "undefined" ? window.location.href.slice(0, 500) : null,
        stack: stack ? String(stack).slice(0, 8000) : null,
      })
      .catch(() => {});
  } catch {
    /* never let the reporter crash the page it is trying to save */
  }
}
