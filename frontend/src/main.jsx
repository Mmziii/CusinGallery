import { StrictMode } from "react";
import { BrowserRouter } from "react-router-dom";
import { createRoot } from "react-dom/client";

import Analytics from "./components/Analytics.jsx";
import App from "./App.jsx";
import { ensureCsrfCookie } from "./services/apiClient.js";
import { applyInitialTheme } from "./utils/theme.js";

// SELF-HOSTED FONTS (Part R2): one family -- Vazirmatn Variable (SIL OFL
// 1.1) -- for UI, headings and prices; weight contrast 400/500/700/800
// instead of a decorative display face. No CDN (slow/blocked in Iran).
import "./styles/fonts.css";

// Design tokens + global base from Phase 1, then the storefront layer.
import "./styles/variables.css";
import "./styles/globals.css";
import "./styles/storefront.css";

// Apply the owner-selected theme BEFORE React mounts. In production the
// Django SPA shell has already inlined the same variables into <head>
// (apps/core/spa.py), so this is a no-op there; in Vite dev / an older
// cached shell it removes the flash of the default palette.
applyInitialTheme();

// The Django session flow requires the csrftoken cookie to exist before
// the first write request; a same-origin GET to /accounts/csrf-token/
// guarantees it's set server-side (withCredentials keeps the session
// cookie flowing too).
ensureCsrfCookie();

// App uses router hooks and an app-level error boundary, so it must stay
// inside a Router. The smoke test in src/App.smoke.test.jsx guards this
// integration and the BrowserRouter below provides the production context.
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
