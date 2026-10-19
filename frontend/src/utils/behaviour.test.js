/**
 * Task 1 frontend tracking: batched, fire-and-forget, privacy-friendly.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  flushEvents,
  getSessionKey,
  isTrackingEnabled,
  resetTrackingForTests,
  trackEvent,
} from "./behaviour";

let originalDnt;

beforeEach(() => {
  resetTrackingForTests();
  window.localStorage.clear();
  document.cookie = "cusin_sk=; path=/; max-age=0";
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: true })));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  Object.defineProperty(window.navigator, "doNotTrack", {
    value: originalDnt,
    configurable: true,
  });
});

function sentBodies() {
  return global.fetch.mock.calls.map(([, options]) => JSON.parse(options.body));
}

describe("behaviour session key", () => {
  it("creates one random key and reuses it", () => {
    const first = getSessionKey();
    const second = getSessionKey();
    expect(first).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
    expect(second).toBe(first);
    expect(window.localStorage.getItem("cusin.analytics.session")).toBe(first);
    expect(document.cookie).toContain(`cusin_sk=${first}`);
  });

  it("never derives the key from the user agent or the clock", () => {
    const key = getSessionKey();
    expect(key).not.toContain("jsdom");
    expect(key.length).toBeLessThanOrEqual(64);
  });
});

describe("batched tracking", () => {
  it("sends queued events in one POST after the delay", () => {
    trackEvent("product_view", { product_id: 12 });
    trackEvent("search", { query: "کتری", results: 0 });
    expect(global.fetch).not.toHaveBeenCalled();

    vi.advanceTimersByTime(3000);

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe("/api/v1/analytics/events/");
    expect(options.method).toBe("POST");
    expect(options.keepalive).toBe(true);
    const body = JSON.parse(options.body);
    expect(body.session_key).toBe(getSessionKey());
    expect(body.events).toEqual([
      { type: "product_view", product_id: 12 },
      { type: "search", query: "کتری", results: 0 },
    ]);
  });

  it("flushes immediately at the batch limit", () => {
    for (let i = 0; i < 20; i += 1) trackEvent("product_view", { product_id: i + 1 });
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(sentBodies()[0].events).toHaveLength(20);
  });

  it("sends only anonymous fields -- no IP, no user agent", () => {
    trackEvent("product_view", { product_id: 5 });
    vi.advanceTimersByTime(3000);
    const body = sentBodies()[0];
    expect(Object.keys(body).sort()).toEqual(["events", "session_key"]);
    expect(Object.keys(body.events[0]).sort()).toEqual(["product_id", "type"]);
    expect(JSON.stringify(body)).not.toMatch(/192\.168|127\.0\.0\.1|jsdom/i);
  });

  it("drops the queue silently when the network fails", () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
    trackEvent("product_view", { product_id: 7 });
    expect(() => vi.advanceTimersByTime(3000)).not.toThrow();
  });

  it("does nothing when Do Not Track is on", () => {
    Object.defineProperty(window.navigator, "doNotTrack", { value: "1", configurable: true });
    expect(isTrackingEnabled()).toBe(false);
    trackEvent("product_view", { product_id: 1 });
    vi.advanceTimersByTime(3000);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("is a no-op with an empty queue", () => {
    expect(() => flushEvents()).not.toThrow();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("uses sendBeacon on page hide when available", () => {
    const beacon = vi.fn(() => true);
    vi.stubGlobal("navigator", { ...window.navigator, sendBeacon: beacon, userAgent: "Mozilla/5.0" });
    trackEvent("product_view", { product_id: 3 });
    flushEvents({ useBeacon: true });
    expect(beacon).toHaveBeenCalledTimes(1);
    expect(beacon.mock.calls[0][0]).toBe("/api/v1/analytics/events/");
  });
});
