import { StrictMode } from "react";
import { BrowserRouter } from "react-router-dom";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import { ensureCsrfCookie } from "./services/apiClient.js";

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
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
);
