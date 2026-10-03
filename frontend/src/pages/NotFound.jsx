import { usePageMeta } from "../hooks/usePageMeta";
/**
 * Generic 404 fallback. A branded Persian error state with proper styling
 * is part of the error-handling phase (see README.md) -- this minimal
 * version exists so unmatched routes never hit a blank screen.
 */
function NotFound() {
  usePageMeta({ title: "صفحه یافت نشد", path: "/404/", noindex: true });
  return (
    <section>
      <h1>۴۰۴</h1>
      <p>صفحه مورد نظر پیدا نشد.</p>
    </section>
  );
}

export default NotFound;
