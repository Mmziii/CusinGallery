/**
 * Part S3 item 10: API client robustness, exercised through the real
 * axios interceptor chain with a scripted fake adapter (same pattern as
 * the cart tests):
 *   - 403 CSRF failure on an unsafe method -> refresh the token once,
 *     retry the SAME request, succeed;
 *   - never more than one retry (no loops);
 *   - 401 on a session-expected request -> auth:session-expired event;
 *   - safe methods (GET) never enter the CSRF retry path.
 */
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import apiClient from "./apiClient";

const calls = [];
let script = [];
const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const step = { method: (config.method || "get").toLowerCase(), url: config.url };
    calls.push(step);
    const behavior = script.shift() || { kind: "ok", data: {} };
    if (behavior.kind === "ok") {
      return { data: behavior.data ?? {}, status: 200, statusText: "OK", headers: {}, config };
    }
    const err = new Error(`Request failed with status code ${behavior.status}`);
    err.config = config;
    err.response = { status: behavior.status, data: behavior.data ?? {} };
    throw err;
  };
});

afterEach(() => {
  calls.length = 0;
  script = [];
});

afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});

describe("apiClient robustness (S3.10)", () => {
  it("refreshes the CSRF cookie and retries once after a CSRF 403", async () => {
    script = [
      { kind: "fail", status: 403, data: { detail: "CSRF Failed: cookie expired." } },
      { kind: "ok", data: { detail: "CSRF cookie set." } }, // the refresh GET
      { kind: "ok", data: { ok: true } }, // the retried PATCH
    ];

    const response = await apiClient.patch("/cart/items/7/", { quantity: 2 });

    expect(response.data.ok).toBe(true);
    expect(calls.map((c) => `${c.method} ${c.url}`)).toEqual([
      "patch /cart/items/7/",
      "get /accounts/csrf/",
      "patch /cart/items/7/",
    ]);
  });

  it("retries at most once, then surfaces the failure", async () => {
    script = [
      { kind: "fail", status: 403, data: { detail: "CSRF Failed." } },
      { kind: "ok", data: {} }, // refresh
      { kind: "fail", status: 403, data: { detail: "CSRF Failed." } }, // retry fails -> stop
    ];

    await expect(apiClient.post("/wishlist/items/", { product_id: 1 })).rejects.toMatchObject({
      response: { status: 403 },
    });
    const patches = calls.filter((c) => c.method === "post" && c.url === "/wishlist/items/");
    expect(patches.length).toBe(2); // original + exactly one retry
  });

  it("does NOT csrf-retry safe methods or non-CSRF 403s", async () => {
    script = [{ kind: "fail", status: 403, data: { detail: "CSRF Failed." } }];
    await expect(apiClient.get("/orders/")).rejects.toMatchObject({ response: { status: 403 } });
    expect(calls.length).toBe(1); // no refresh, no retry

    calls.length = 0;
    script = [{ kind: "fail", status: 403, data: { detail: "شما اجازه این کار را ندارید." } }];
    await expect(apiClient.post("/orders/checkout/", {})).rejects.toMatchObject({
      response: { status: 403 },
    });
    expect(calls.length).toBe(1);
  });

  it("broadcasts auth:session-expired on an unexpected 401", async () => {
    let fired = false;
    const listener = () => {
      fired = true;
    };
    window.addEventListener("auth:session-expired", listener);
    script = [{ kind: "fail", status: 401, data: { detail: "Authentication credentials were not provided." } }];

    await expect(apiClient.get("/orders/")).rejects.toMatchObject({ response: { status: 401 } });
    expect(fired).toBe(true);
    window.removeEventListener("auth:session-expired", listener);
  });

  it("does NOT broadcast session-expired for anonymous-probe endpoints", async () => {
    let fired = false;
    const listener = () => {
      fired = true;
    };
    window.addEventListener("auth:session-expired", listener);
    script = [{ kind: "fail", status: 401, data: { detail: "Not logged in." } }];

    await expect(apiClient.get("/accounts/me/")).rejects.toMatchObject({ response: { status: 401 } });
    expect(fired).toBe(false);
    window.removeEventListener("auth:session-expired", listener);
  });
});
