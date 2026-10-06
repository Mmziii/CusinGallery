/**
 * Analytics hook tests (Part 4): env unset -> no script at all; env set
 * -> the script is injected (storefront only -- admin/callback are
 * server templates that never mount the SPA, asserted on the backend
 * in apps/core/test_analytics.py). Do Not Track is respected.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Analytics from "./components/Analytics";

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  document.head.querySelectorAll("script[data-cusin-analytics]").forEach((s) => s.remove());
  Object.defineProperty(window.navigator, "doNotTrack", { value: "0", configurable: true });
});

describe("analytics injection", () => {
  it("loads nothing when the env is unset", () => {
    vi.stubEnv("VITE_ANALYTICS_SCRIPT_URL", "");
    render(<Analytics />);
    expect(document.head.querySelector("script[data-cusin-analytics]")).toBeNull();
  });

  it("injects the configured script with the site id", () => {
    vi.stubEnv("VITE_ANALYTICS_SCRIPT_URL", "https://stats.example.com/script.js");
    vi.stubEnv("VITE_ANALYTICS_SITE_ID", "cusin.ir");
    render(<Analytics />);
    const script = document.head.querySelector("script[data-cusin-analytics]");
    expect(script).not.toBeNull();
    expect(script.getAttribute("src")).toBe("https://stats.example.com/script.js");
    expect(script.getAttribute("data-domain")).toBe("cusin.ir");
  });

  it("respects Do Not Track", () => {
    Object.defineProperty(window.navigator, "doNotTrack", { value: "1", configurable: true });
    vi.stubEnv("VITE_ANALYTICS_SCRIPT_URL", "https://stats.example.com/script.js");
    render(<Analytics />);
    expect(document.head.querySelector("script[data-cusin-analytics]")).toBeNull();
  });
});
