import { expect, it } from "vitest";
import { faDigits, faDateTime, deliveryDays, deliveryRange } from "./faDigits";
it("localizes display names and counts without grouping", () => {
 expect(faDigits("سرویس 24 پارچه")).toBe("سرویس ۲۴ پارچه");
 expect(faDigits(1250)).toBe("۱۲۵۰");
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
