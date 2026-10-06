import { useEffect } from "react";

/**
 * Optional privacy-friendly analytics (Part 4).
 *
 * Controlled entirely by build env (VITE_ANALYTICS_SCRIPT_URL /
 * VITE_ANALYTICS_SITE_ID, wired from ANALYTICS_* in compose): unset ->
 * this component renders NOTHING and no request is made. It sets no
 * cookies of its own, respects Do Not Track, and only ever mounts in
 * the storefront SPA -- the Django admin and the payment callback
 * pages are server-rendered templates that never include it.
 *
 * Works with any Plausible/Matomo-style snippet that reads
 * data-domain; the store owner picks the provider in DEPLOY.md.
 */
function Analytics() {
  const scriptUrl = import.meta.env.VITE_ANALYTICS_SCRIPT_URL || "";
  const siteId = import.meta.env.VITE_ANALYTICS_SITE_ID || "";

  useEffect(() => {
    if (!scriptUrl) return undefined;
    if (typeof navigator !== "undefined" && navigator.doNotTrack === "1") {
      return undefined; // respect DNT: load nothing
    }
    const script = document.createElement("script");
    script.defer = true;
    script.src = scriptUrl;
    if (siteId) script.setAttribute("data-domain", siteId);
    script.setAttribute("data-cusin-analytics", "true");
    document.head.appendChild(script);
    return () => script.remove();
  }, [scriptUrl, siteId]);

  return null;
}

export default Analytics;
