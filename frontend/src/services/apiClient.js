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
apiClient.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(error)
);

/**
 * Ensures the csrftoken cookie exists before the first unsafe request.
 * Call once on app start -- cheap (GET /accounts/csrf/), idempotent.
 */
export function ensureCsrfCookie() {
  return apiClient.get("/accounts/csrf/").catch(() => null);
}

export default apiClient;
