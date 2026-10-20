import { expect, it } from "vitest";
import { faDigits, hoursRange, latinDigits, faDate, faDateTime, deliveryDays, deliveryRange } from "./faDigits";
it("localizes display names and counts without grouping", () => {
 expect(faDigits("سرویس 24 پارچه")).toBe("سرویس ۲۴ پارچه");
 expect(faDigits(1250)).toBe("۱۲۵۰");
 expect(latinDigits("۰۹۳۹۶۹۸۶۴۲۸")).toBe("09396986428");
});
it("zero-pads Jalali month and day across storefront date surfaces", () => {
 expect(faDate("2026-10-15T01:55:00Z")).toMatch(/۱۴۰۵\/۰۷\/۲۳/);
});
it("formats Persian date/time with a Persian comma", () => {
 expect(faDateTime("2026-10-15T01:55:00Z")).toContain("، ساعت ");
 expect(faDateTime("2026-10-15T01:55:00Z")).not.toMatch(/[0-9,]/);
});
it("collapses equal delivery dates and day windows", () => {
 expect(deliveryRange("2026-10-15", "2026-10-15")).not.toContain(" تا ");
 expect(deliveryRange("2026-10-15", "2026-10-17")).toContain(" تا ");
 expect(deliveryDays(1,1)).toBe("تحویل ۱ روزه");
 expect(deliveryDays(3,5)).toBe("تحویل ۳ تا ۵ روز کاری");
});

it("rewrites bare HH:MM-HH:MM hours as «HH:MM تا HH:MM»", () => {
 expect(hoursRange("10:00-21:00")).toBe("۱۰:۰۰ تا ۲۱:۰۰");
 expect(hoursRange("9:00-13:30")).toBe("۹:۰۰ تا ۱۳:۳۰");
 expect(hoursRange("10:00 - 21:00")).toBe("۱۰:۰۰ تا ۲۱:۰۰");
 expect(hoursRange("10:00–21:00")).toBe("۱۰:۰۰ تا ۲۱:۰۰");
 expect(hoursRange("۱۰:۰۰-۲۱:۰۰")).toBe("۱۰:۰۰ تا ۲۱:۰۰");
 // A range inside a longer sentence: only the range is rewritten.
 expect(hoursRange("شنبه تا پنجشنبه، 10:00-21:00")).toBe("شنبه تا پنجشنبه، ۱۰:۰۰ تا ۲۱:۰۰");
 // Free text and values that already say «تا» keep their shape.
 expect(hoursRange("شنبه تا چهارشنبه ۱۰ تا ۱۹")).toBe("شنبه تا چهارشنبه ۱۰ تا ۱۹");
 expect(hoursRange("")).toBe("");
 // A date range is not an hours range.
 expect(hoursRange("1405/07/01-1405/07/02")).toBe("۱۴۰۵/۰۷/۰۱-۱۴۰۵/۰۷/۰۲");
});
