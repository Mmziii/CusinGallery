/**
 * Privacy-friendly behaviour tracking (Task 1).
 *
 * One batched, fire-and-forget POST to /api/v1/analytics/events/:
 *   - events are queued and sent in groups (or on page hide with
 *     navigator.sendBeacon);
 *   - nothing here ever throws, blocks rendering or shows an error --
 *     a failed report is simply dropped;
 *   - the only identifier is a RANDOM key stored in localStorage
 *     («cusin.analytics.session»), mirrored into a cookie so the backend
 *     can attach the same anonymous session to server-side events. No IP,
 *     no fingerprint, no user agent is ever sent.
 *   - Do Not Track and obvious bots disable it entirely.
 *
 * Server-side events (order placed/paid, authenticated add-to-cart) do
 * not go through this module; they are written by Django so they can
 * never be lost.
 */
const SESSION_KEY = "cusin.analytics.session";
const COOKIE_NAME = "cusin_sk";
const QUEUE_LIMIT = 20;
const FLUSH_DELAY_MS = 3000;
const MAX_BATCH = 25;
const KEY_RE = /^[A-Za-z0-9_-]{8,64}$/;
const BOT_RE =
  /bot|crawler|spider|slurp|bingpreview|headless|phantomjs|selenium|puppeteer|playwright|python-requests|curl\/|wget|monitor|lighthouse/i;

let queue = [];
let timer = null;
let listenersBound = false;

function apiBase() {
  const base = import.meta.env?.VITE_API_BASE_URL || "/api/v1";
  return `${base.replace(/\/$/, "")}/analytics/events/`;
}

function randomKey() {
  const cryptoObj = typeof window !== "undefined" ? window.crypto : undefined;
  if (cryptoObj?.randomUUID) return cryptoObj.randomUUID().replace(/-/g, "");
  if (cryptoObj?.getRandomValues) {
    const bytes = cryptoObj.getRandomValues(new Uint8Array(18));
    return Array.from(bytes, (b) => b.toString(36).padStart(2, "0")).join("").slice(0, 32);
  }
  return `anon${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 32);
}

/** Is tracking allowed in this browser right now? */
export function isTrackingEnabled() {
  if (typeof window === "undefined" || typeof navigator === "undefined") return false;
  if (navigator.webdriver) return false;
  const dnt =
    navigator.doNotTrack || window.doNotTrack || navigator.msDoNotTrack;
  if (dnt === "1" || dnt === "yes") return false;
  if (BOT_RE.test(navigator.userAgent || "")) return false;
  return true;
}

/** The anonymous random session key (created on first use, never an IP). */
export function getSessionKey() {
  if (typeof window === "undefined") return "";
  try {
    const stored = window.localStorage.getItem(SESSION_KEY);
    if (stored && KEY_RE.test(stored)) return stored;
    const key = randomKey();
    if (!KEY_RE.test(key)) return "";
    window.localStorage.setItem(SESSION_KEY, key);
    // Same key in a cookie so Django can read it on server-rendered
    // requests too (apps/analytics/tracking.py). Not a secret: it is a
    // random anonymous id, exactly like the one in localStorage.
    document.cookie = `${COOKIE_NAME}=${key}; path=/; max-age=31536000; SameSite=Lax`;
    return key;
  } catch {
    // Private mode / storage disabled: tracking simply stays off.
    return "";
  }
}

function bindFlushListeners() {
  if (listenersBound || typeof window === "undefined") return;
  listenersBound = true;
  const flushOnHide = () => {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") {
      flushEvents({ useBeacon: true });
    }
  };
  window.addEventListener("pagehide", () => flushEvents({ useBeacon: true }));
  document.addEventListener?.("visibilitychange", flushOnHide);
}

/**
 * Queue one event. Safe to call from anywhere: it never throws and never
 * waits on the network.
 *
 * @param {string} type one of product_view | add_to_cart |
 *   remove_from_cart | wishlist_add | search | checkout_started
 * @param {object} payload optional {product_id, query, results}
 */
export function trackEvent(type, payload = {}) {
  try {
    if (!type || !isTrackingEnabled()) return;
    const event = { type };
    if (payload.product_id) event.product_id = Number(payload.product_id);
    if (payload.query) event.query = String(payload.query).slice(0, 200);
    if (payload.results !== undefined && payload.results !== null) {
      event.results = Math.max(0, Number(payload.results) || 0);
    }
    queue.push(event);
    bindFlushListeners();
    if (queue.length >= QUEUE_LIMIT) {
      flushEvents();
      return;
    }
    if (!timer) {
      timer = setTimeout(() => {
        timer = null;
        flushEvents();
      }, FLUSH_DELAY_MS);
    }
  } catch {
    /* tracking must never break the page it measures */
  }
}

/** Send everything currently queued. Fire-and-forget, never throws. */
export function flushEvents({ useBeacon = false } = {}) {
  try {
    if (!queue.length) return;
    if (!isTrackingEnabled()) {
      queue = [];
      return;
    }
    const sessionKey = getSessionKey();
    if (!sessionKey) {
      queue = [];
      return;
    }
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    const events = queue.slice(0, MAX_BATCH);
    queue = queue.slice(MAX_BATCH);
    const body = JSON.stringify({ session_key: sessionKey, events });
    const url = apiBase();

    if (useBeacon && typeof navigator !== "undefined" && navigator.sendBeacon) {
      const blob = new Blob([body], { type: "application/json" });
      navigator.sendBeacon(url, blob);
      return;
    }
    if (typeof fetch !== "function") return;
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      keepalive: true,
      body,
    }).catch(() => {});
  } catch {
    /* never surface a tracking failure */
  }
}

/** Test helper: forget queued events/timers/listener state. */
export function resetTrackingForTests() {
  queue = [];
  if (timer) clearTimeout(timer);
  timer = null;
  listenersBound = false;
}
