import { describe, expect, it } from "vitest";

import { isExpressEligible } from "./shipping";

describe("express delivery destination", () => {
  it.each([
    ["تهران", "تهران"], [" Tehran ", "TEHRAN"], ["تهران", "شهرستان تهران"], ["تهران", "شهرستان  تهران"],
  ])("accepts Tehran city in Tehran province: %s / %s", (province, city) => {
    expect(isExpressEligible(province, city)).toBe(true);
  });
  it.each([
    ["تهران", "شهریار"], ["تهران", "ری"], ["تهران", "پردیس"], ["تهران", "دماوند"],
    ["البرز", "تهران"], ["تهران", "تهرانپارس"], ["تهران", "تهران - ری"], [null, null], ["تهران", ""],
  ])("does not mistake a province, substring or missing address for Tehran city: %s / %s", (province, city) => {
    expect(isExpressEligible(province, city)).toBe(false);
  });
});
