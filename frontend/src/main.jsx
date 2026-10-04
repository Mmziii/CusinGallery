import { StrictMode } from "react";
import { BrowserRouter } from "react-router-dom";
import { createRoot } from "react-dom/client";

import Analytics from "./components/Analytics.jsx";
import App from "./App.jsx";
import { ensureCsrfCookie } from "./services/apiClient.js";

// SELF-HOSTED FONTS (Part R2): one family -- Vazirmatn Variable (SIL OFL
// 1.1) -- for UI, headings and prices; weight contrast 400/500/700/800
// instead of a decorative display face. No CDN (slow/blocked in Iran).
import "./styles/fonts.css";

// Design tokens + global base from Phase 1, then the storefront layer.
import "./styles/variables.css";
import "./styles/globals.css";
import "./styles/storefront.css";

// The Django session flow requires the csrftoken cookie to exist before
// the first write request; a same-origin GET to /accounts/csrf-token/
// guarantees it's set server-side (withCredentials keeps the session
// cookie flowing too).
ensureCsrfCookie();

// App is a bare <Routes> tree: react-router needs a Router context
// above it or every hook (useSearchParams, useParams, <Link>) throws
// and the page renders WHITE. This wrapper is the fix for that bug --
// the smoke test in src/App.smoke.test.jsx guards it.
createRoot(document.getElementById("root")).render(
  <StrictMode>
    {/* Optional, env-controlled, DNT-respecting; absent from admin and
        payment-callback pages (server templates never mount the SPA). */}
    <Analytics />
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
);
