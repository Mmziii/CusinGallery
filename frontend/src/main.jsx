import { StrictMode } from "react";
import { BrowserRouter } from "react-router-dom";
import { createRoot } from "react-dom/client";

import Analytics from "./components/Analytics.jsx";
import App from "./App.jsx";
import { ensureCsrfCookie } from "./services/apiClient.js";

// SELF-HOSTED FONTS (Part 3): Vazirmatn variable for body/UI and Lalezar
// for display headings/brand -- both SIL Open Font License, bundled via
// fontsource (no Google Fonts/CDN: slow or blocked in Iran). The
// @font-face rules set font-display: swap and unicode-range subsets.
import "@fontsource-variable/vazirmatn";
import "@fontsource/lalezar";

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
