import { useEffect, useRef } from "react";
import { Outlet, useLocation } from "react-router-dom";

import FloatingContact from "../components/FloatingContact";
import Footer from "../components/Footer";
import Header from "../components/Header";
import Toaster from "../components/Toaster";
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
 * Shared page shell (Part 3): sticky header, route-transition fade on
 * the content, footer, toasts and the floating contact cluster.
 */
function MainLayout() {
  const location = useLocation();
  const mainRef = useRef(null);

  // Smooth route-transition fade: retrigger a CSS animation per path.
  useEffect(() => {
    const node = mainRef.current;
    if (!node) return;
    node.classList.remove("route-fade");
    // force reflow so the animation restarts
    void node.offsetWidth;
    node.classList.add("route-fade");
    window.scrollTo({ top: 0 });
  }, [location.pathname]);

  return (
    <div className="app-shell">
      <Header />
      <MergeNotice />

      <main className="app-shell__main" ref={mainRef}>
        <div className="container">
          <Outlet />
        </div>
      </main>

      <Footer />
      <FloatingContact />
      <Toaster />
    </div>
  );
}

export default MainLayout;
