import { usePageMeta } from "../hooks/usePageMeta";
/**
 * Generic 404 fallback. A branded Persian error state with proper styling
 * is part of the error-handling phase (see README.md) -- this minimal
 * version exists so unmatched routes never hit a blank screen.
 */
function NotFound() {
  usePageMeta({ title: "صفحه یافت نشد", path: "/404/", noindex: true });
  return (
    <section className="notfound">
      <h1>۴۰۴</h1>
      <p>صفحه مورد نظر پیدا نشد؛ شاید نشانی عوض شده است.</p>
      <a className="btn btn--primary" href="/">بازگشت به فروشگاه</a>
    </section>
  );
}

export default NotFound;
