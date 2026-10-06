import axios from "axios";

/**
 * Single axios instance every feature-specific service module (products,
 * cart, orders, ...) imports instead of creating its own client.
 * Auth-token attachment, CSRF handling, and error normalization live
 * here exactly once.
 *
 * Authentication is session + CSRF (the backend deliberately does NOT
 * use JWT), so the only client-side requirement is: read the csrftoken
 * cookie and send it back as the X-CSRFToken header on unsafe methods.
 *
 * VITE_API_BASE_URL must be set at build time (see frontend/.env.example).
 * Falls back to a same-origin relative path so local development works
 * even before .env is configured, matching the Nginx reverse-proxy
 * layout used in production (see nginx/conf.d/cusin.conf).
 */
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  withCredentials: true,
  // Part S3 item 10: a request may never hang forever -- 20 s and the
  // caller gets the normal (Persian) error flow with a retry action.
  timeout: 20000,
  headers: {
    "Content-Type": "application/json",
  },
});

export function getCookie(name) {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

const UNSAFE_METHODS = new Set(["post", "put", "patch", "delete"]);

apiClient.interceptors.request.use((config) => {
  if (UNSAFE_METHODS.has((config.method || "get").toLowerCase())) {
    const token = getCookie("csrftoken");
    if (token) {
      config.headers["X-CSRFToken"] = token;
    }
  }
  return config;
});

// Normalizes rejections so calling code has one consistent shape to
// catch (see utils/apiError.js); nothing is swallowed.
//
// Part R3: a 401 on a request that EXPECTED a session (anything except the
// anonymous probes: /me/, login, register, csrf, password-reset) means the
// session expired mid-use. We broadcast an event the auth store listens
// to so the user lands on the login page with a clear Persian notice
// instead of silently logged-out confusion.
const ANONYMOUS_SAFE = /\/accounts\/(me|login|register|csrf|password-reset)/;
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const url = error?.config?.url || "";
    const status = error?.response?.status;
    const method = (error?.config?.method || "get").toLowerCase();

    // Part S3 item 10: a 403 on an UNSAFE method is most often a CSRF
    // failure (expired/rotated csrftoken cookie), NOT an authorization
    // problem -- refresh the cookie once and retry the same request.
    // The _csrfRetried flag guarantees a single retry (no loops).
    if (status === 403 && UNSAFE_METHODS.has(method) && !error.config._csrfRetried) {
      const detail = String(error?.response?.data?.detail || "");
      if (detail.toUpperCase().includes("CSRF") || detail === "") {
        error.config._csrfRetried = true;
        await ensureCsrfCookie();
        // transformRequest already ran once, so config.data is a JSON
        // string; parse it back so the retry serializes it exactly once.
        if (typeof error.config.data === "string") {
          try {
            error.config.data = JSON.parse(error.config.data);
          } catch {
            /* leave as-is; better a hard failure than mangled data */
          }
        }
        return apiClient.request(error.config);
      }
    }

    if (status === 401 && !ANONYMOUS_SAFE.test(url)) {
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("auth:session-expired"));
      }
    }
    return Promise.reject(error);
  }
);

/**
 * Ensures the csrftoken cookie exists before the first unsafe request.
 * Call once on app start -- cheap (GET /accounts/csrf/), idempotent.
 */
export function ensureCsrfCookie() {
  return apiClient.get("/accounts/csrf/").catch(() => null);
}

export default apiClient;
