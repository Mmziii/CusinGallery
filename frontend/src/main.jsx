import { StrictMode } from "react";
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

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);
