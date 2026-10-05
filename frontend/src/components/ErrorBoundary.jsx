import { Component } from "react";
import PropTypes from "prop-types";
import { Link } from "react-router-dom";

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

  componentDidCatch(error, info) {
    // Visible in the owner's devtools; the user sees the friendly page.
    console.error("render error caught by ErrorBoundary:", error, info?.componentStack);
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
          <Link className="btn btn--outline" to="/">
            بازگشت به صفحه اصلی
          </Link>
        </div>
      </div>
    );
  }
}

ErrorBoundary.propTypes = { children: PropTypes.node };

export default ErrorBoundary;
