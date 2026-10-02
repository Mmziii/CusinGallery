/**
 * Generic 404 fallback. A branded Persian error state with proper styling
 * is part of the error-handling phase (see README.md) -- this minimal
 * version exists so unmatched routes never hit a blank screen.
 */
function NotFound() {
  return (
    <section>
      <h1>۴۰۴</h1>
      <p>صفحه مورد نظر پیدا نشد.</p>
    </section>
  );
}

export default NotFound;
