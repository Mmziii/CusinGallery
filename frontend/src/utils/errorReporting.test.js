/**
 * Part S3 item 9: the error reporter's safety contract.
 *  - VITE_SENTRY_DSN empty (the default, and the test environment) =>
 *    reporting is OFF and reportFrontendError makes ZERO requests.
 *  - VITE_SENTRY_DSN set => the report is POSTed to the backend capture
 *    endpoint with size-capped fields.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("error reporting gate (S3.9)", () => {
  it("is OFF without VITE_SENTRY_DSN: nothing is ever sent", async () => {
    const apiClient = (await import("../services/apiClient")).default;
    const spy = vi.fn(async (config) => ({ data: {}, status: 200, statusText: "OK", headers: {}, config }));
    apiClient.defaults.adapter = spy;

    const { reportFrontendError, isReportingEnabled } = await import("./errorReporting");
    expect(isReportingEnabled()).toBe(false);

    reportFrontendError({ message: "boom", component: "X", stack: "s" });
    // Give any (incorrectly scheduled) request a chance to fire.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(spy).not.toHaveBeenCalled();
  });

  it("sends a capped report to the capture endpoint when enabled", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "https://examplePublicKey@o0.ingest.sentry.io/0");
    vi.resetModules();

    const apiClient = (await import("../services/apiClient")).default;
    const sent = [];
    apiClient.defaults.adapter = async (config) => {
      sent.push(config);
      return { data: { detail: "گزارش دریافت شد." }, status: 202, statusText: "Accepted", headers: {}, config };
    };

    const { reportFrontendError, isReportingEnabled } = await import("./errorReporting");
    expect(isReportingEnabled()).toBe(true);

    reportFrontendError({ message: "m".repeat(5000), component: "ProductDetailPage", stack: "s".repeat(20000) });
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(sent.length).toBe(1);
    expect(sent[0].url).toBe("/site/report-error/");
    const body = typeof sent[0].data === "string" ? JSON.parse(sent[0].data) : sent[0].data;
    expect(body.message.length).toBeLessThanOrEqual(2000);
    expect(body.stack.length).toBeLessThanOrEqual(8000);
    expect(body.component).toBe("ProductDetailPage");
  });
});
