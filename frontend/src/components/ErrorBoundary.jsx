import { Component } from "react";
import PropTypes from "prop-types";
import { Link } from "react-router-dom";

import { reportFrontendError } from "../utils/errorReporting";

/**
 * React error boundary (Part R3): a render crash anywhere inside shows a
 * friendly Persian "مشکلی پیش آمد" page with retry + back-home actions,
 * never a blank white page. Mounted twice: around the whole <App /> and
 * around each routed page (MainLayout's <Outlet />), so a crash in one
 * page keeps the header/footer usable.
 */
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidUpdate(previousProps) {
    // Route boundaries stay mounted while <Outlet> changes. Resetting on
    // location (including query-string) changes prevents one broken route
    // from trapping the shopper on this fallback, while the retry button
    // below remains useful without any navigation.
    if (previousProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error, info) {
    // Visible in the owner's devtools; the user sees the friendly page.
    console.error("render error caught by ErrorBoundary:", error, info?.componentStack);
    // Part S3 item 9: forward to the backend capture endpoint (no-op
    // unless VITE_SENTRY_DSN was set at build time).
    reportFrontendError({
      message: error?.message || String(error),
      component: info?.componentStack?.split("\n").find(Boolean)?.trim() || null,
      stack: error?.stack || null,
    });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="error-boundary" role="alert">
        <h1>مشکلی پیش آمد</h1>
        <p>
          نمایش این بخش با خطا مواجه شد. دوباره تلاش کنید؛ اگر مشکل ادامه داشت، به
          صفحهٔ اصلی برگردید.
        </p>
        <div className="error-boundary__actions">
          <button type="button" className="btn btn--primary" onClick={() => this.setState({ error: null })}>
            تلاش دوباره
          </button>
          {/* Keep recovery navigation as ordinary links: they work from the
              route boundary and from the app-level fallback alike. */}
          <Link className="btn btn--outline" to="/">
            بازگشت به صفحه اصلی
          </Link>
          <Link className="btn btn--outline" to="/shop/">
            رفتن به فروشگاه
          </Link>
        </div>
      </div>
    );
  }
}

ErrorBoundary.propTypes = {
  children: PropTypes.node,
  // MainLayout/App supply pathname+search. It is optional so the component
  // also remains useful for local, manually retried boundaries.
  resetKey: PropTypes.string,
};

export default ErrorBoundary;
