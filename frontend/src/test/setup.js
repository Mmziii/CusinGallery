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

// jsdom implements neither scrolling API. AddressForm/CheckoutPage call
// scrollIntoView() to bring the first invalid field into view and the
// shop page saves/restores the listing scroll position, so both are
// stubbed here (same policy as matchMedia/IntersectionObserver above)
// instead of leaving the production code to throw "not a function" --
// vitest 4 reports such a rejection as an unhandled error.
window.scrollTo = () => {};
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// --- fake API ----------------------------------------------------------------
const EMPTY = {
  "^/accounts/me/$": { user: null, detail: "Not logged in." },
  "^/accounts/csrf/$": { detail: "CSRF cookie set." },
  "^/site/settings/": {},
  "^/banners/daily-deals/": { server_now: new Date().toISOString(), results: [] },
  "^/banners/": [],
  "^/categories/tree": [],
  "^/categories/": [],
  "^/products/": { count: 0, next: null, previous: null, results: [] },
  "^/cart/": { items: [], subtotal: 0, total: 0, quantity: 0 },
  "^/orders/": { count: 0, next: null, previous: null, results: [] },
  "^/shipping-methods/": [],
};

// Tiny in-memory "server cart" for the merge endpoint so store tests
// can exercise summing/capping/skip reporting and token idempotency.
let serverCart = [];
const seenTokens = new Set();

apiClient.defaults.adapter = async (config) => {
  const url = `${config.url || ""}`;
  const method = (config.method || "get").toLowerCase();

  if (url.endsWith("/cart/merge/") && method === "post") {
    const body = JSON.parse(config.data || "{}");
    const lines = Array.isArray(body.lines) ? body.lines : [];
    // A line for product 9999 simulates a total merge outage (500), so
    // tests can verify the "never lose the guest cart" rule.
    if (lines.some((l) => l.product_id === 9999)) {
      const error = new Error("merge outage");
      error.response = { status: 500, data: { detail: "boom" } };
      throw error;
    }
    const report = { merged: [], adjusted: [], skipped: [], replayed: false };
    if (body.merge_token && seenTokens.has(body.merge_token)) {
      report.replayed = true;
    } else {
      if (body.merge_token) seenTokens.add(body.merge_token);
      for (const line of lines) {
        // product 9000+ = "inactive", 8000+ = "out of stock" in tests.
        if (line.product_id >= 9000) {
          report.skipped.push({ ...line, reason: "unavailable" });
          continue;
        }
        if (line.product_id >= 8000) {
          report.skipped.push({ ...line, reason: "out_of_stock" });
          continue;
        }
        const cap = line.product_id === 7001 ? 2 : 99; // 7001 => stock cap
        const existing = serverCart.find(
          (l) => l.product_id === line.product_id && l.variant_id === (line.variant_id ?? null)
        );
        const current = existing ? existing.quantity : 0;
        const target = Math.min(current + line.quantity, cap);
        const added = target - current;
        if (added < 1) {
          report.skipped.push({ ...line, reason: "stock_exhausted" });
        } else {
          if (existing) existing.quantity = target;
          else serverCart.push({ product_id: line.product_id, variant_id: line.variant_id ?? null, quantity: target });
          (added < line.quantity ? report.adjusted : report.merged).push({
            product_id: line.product_id,
            variant_id: line.variant_id ?? null,
            requested: line.quantity,
            added,
          });
        }
      }
    }
    return {
      data: { cart: { items: serverCart, item_count: serverCart.reduce((n, l) => n + l.quantity, 0) }, report },
      status: 200, statusText: "OK", headers: {}, config,
    };
  }

  for (const [pattern, data] of Object.entries(EMPTY)) {
    if (new RegExp(pattern).test(url)) {
      return { data, status: 200, statusText: "OK", headers: {}, config };
    }
  }
  // Anything unlisted: empty object -- pages must tolerate it or the
  // smoke test fails loudly, which is exactly the regression we guard.
  return { data: {}, status: 200, statusText: "OK", headers: {}, config };
};
