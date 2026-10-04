/**
 * Vitest setup (Part 0): jsdom polyfills for the browser APIs the
 * storefront uses, plus ONE fake axios adapter that answers every API
 * call with an empty-but-valid payload. This keeps the smoke test honest
 * about what it guards (routing + rendering, not API behaviour -- that
 * is covered by the Django suite and the live E2E script) while never
 * touching the network.
 */
import "@testing-library/dom";

import apiClient from "../services/apiClient";

// --- browser API polyfills missing from jsdom -------------------------------
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

if (!window.IntersectionObserver) {
  class IntersectionObserverStub {
    constructor(callback) {
      this.callback = callback;
    }
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  }
  window.IntersectionObserver = IntersectionObserverStub;
}

if (!window.ResizeObserver) {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  window.ResizeObserver = ResizeObserverStub;
}

window.scrollTo = window.scrollTo || (() => {});

// --- fake API ----------------------------------------------------------------
const EMPTY = {
  "^/accounts/me/$": { user: null, detail: "Not logged in." },
  "^/accounts/csrf/$": { detail: "CSRF cookie set." },
  "^/banners/daily-deals/": { server_now: new Date().toISOString(), results: [] },
  "^/banners/": [],
  "^/categories/tree": [],
  "^/categories/": [],
  "^/products/": { count: 0, next: null, previous: null, results: [] },
  "^/cart/": { items: [], subtotal: 0, total: 0, quantity: 0 },
  "^/orders/": { count: 0, next: null, previous: null, results: [] },
  "^/shipping-methods/": [],
};

apiClient.defaults.adapter = async (config) => {
  const url = `${config.url || ""}`;
  for (const [pattern, data] of Object.entries(EMPTY)) {
    if (new RegExp(pattern).test(url)) {
      return { data, status: 200, statusText: "OK", headers: {}, config };
    }
  }
  // Anything unlisted: empty object -- pages must tolerate it or the
  // smoke test fails loudly, which is exactly the regression we guard.
  return { data: {}, status: 200, statusText: "OK", headers: {}, config };
};
