/**
 * Part S3 item 10: central error normalization. Every failure shape must
 * become ONE Persian sentence -- never a raw object, never
 * "[object Object]", never English axios boilerplate.
 */
import { describe, expect, it } from "vitest";

import { normalizeApiError } from "./apiError";

const resp = (status, data) => ({ response: { status, data } });

describe("normalizeApiError (S3.10)", () => {
  it("network failure -> connection message", () => {
    const n = normalizeApiError(new Error("Network Error"));
    expect(n.isNetworkError).toBe(true);
    expect(n.message).toContain("اتصال به سرور برقرار نشد");
  });

  it("timeout -> server-too-slow message (not the network one)", () => {
    const err = new Error("timeout of 20000ms exceeded");
    err.code = "ECONNABORTED";
    const n = normalizeApiError(err);
    expect(n.isNetworkError).toBe(true);
    expect(n.message).toContain("پاسخ سرور طول کشید");
  });

  it("429 -> friendly rate-limit message", () => {
    const n = normalizeApiError(resp(429, { detail: "Request was throttled." }));
    expect(n.message).toContain("تعداد درخواست‌ها");
    expect(n.isAuthError).toBe(false);
  });

  it("5xx -> server error message regardless of body shape", () => {
    for (const data of [undefined, null, "<html>bad gateway</html>", { detail: "boom" }]) {
      const n = normalizeApiError(resp(502, data));
      expect(n.message).toContain("خطایی در سرور رخ داد");
    }
  });

  it("401/403 -> auth message", () => {
    expect(normalizeApiError(resp(401, {})).isAuthError).toBe(true);
    expect(normalizeApiError(resp(403, {})).message).toContain("وارد حساب کاربری");
  });

  it("400 field errors keep the field map and pick a string message", () => {
    const n = normalizeApiError(resp(400, { quantity: ["فقط ۳ عدد موجود است."] }));
    expect(n.fieldErrors.quantity[0]).toContain("موجود");
    expect(n.message).toContain("موجود");
  });

  it("never renders an object as the message ([object Object] guard)", () => {
    const shapes = [
      resp(400, { nested: { deep: { worse: 1 } } }), // no string anywhere
      resp(400, { detail: { weird: true } }), // detail that is NOT a string
      resp(500, { detail: { nested: true } }),
      resp(404, { detail: ["not", "a", "string"] }),
      resp(418, "plain text body"),
    ];
    for (const shape of shapes) {
      const n = normalizeApiError(shape);
      expect(typeof n.message).toBe("string");
      expect(n.message.length).toBeGreaterThan(3);
      expect(n.message).not.toContain("[object Object]");
    }
  });
});
