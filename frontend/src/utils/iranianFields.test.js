import { describe, expect, it } from "vitest";
import { isValidIranianPhone, normalizePhone } from "./iranianFields";
describe("mobile-only customer phone fields", () => {
  it.each(["۰۹۱۲۳۴۵۶۷۸۹", "٠٩١٢٣٤٥٦٧٨٩", "+989123456789", "00989123456789"])("normalizes %s", value => {
    expect(normalizePhone(value)).toBe("09123456789");
    expect(isValidIranianPhone(value)).toBe(true);
  });
  it.each(["02112345678", "123", "091234567890"])("rejects %s", value => expect(isValidIranianPhone(value)).toBe(false));
});
