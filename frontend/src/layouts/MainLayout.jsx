import { useEffect } from "react";
import { Outlet } from "react-router-dom";

import Footer from "../components/Footer";
import Header from "../components/Header";
import useCartStore from "../store/useCartStore";

/**
 * Dismissible notice after a guest-cart merge (Part 1): tells the
 * shopper when lines were capped by stock or dropped as unavailable.
 */
function MergeNotice() {
  const report = useCartStore((s) => s.lastMergeReport);
  const clear = useCartStore((s) => s.clearMergeNotice);

  useEffect(() => {
    if (!report) return undefined;
    const timer = setTimeout(clear, 12000);
    return () => clearTimeout(timer);
  }, [report, clear]);

  if (!report || report.replayed) return null;
  const adjusted = report.adjusted || [];
  const skipped = report.skipped || [];
  if (adjusted.length === 0 && skipped.length === 0) return null;

  return (
    <div className="container merge-notice" role="status">
      <span>
        سبد مهمان شما به حساب منتقل شد
        {adjusted.length > 0 ? "؛ تعداد برخی اقلام به‌دلیل موجودی محدود شد" : ""}
        {skipped.length > 0 ? " و برخی اقلام ناموجود/نامعتبر حذف شدند" : ""}.
      </span>
      <button type="button" className="merge-notice__close" onClick={clear} aria-label="بستن پیام">
        ×
      </button>
    </div>
  );
}

/**
 * Shared page shell: real header (search, nav, account, cart), content
 * outlet, and footer. Every route renders inside this unless a future
 * flow (e.g. a distraction-free checkout) needs its own layout.
 */
function MainLayout() {
  return (
    <div className="app-shell">
      <Header />
      <MergeNotice />

      <main className="app-shell__main">
        <div className="container">
          <Outlet />
        </div>
      </main>

      <Footer />
    </div>
  );
}

export default MainLayout;
