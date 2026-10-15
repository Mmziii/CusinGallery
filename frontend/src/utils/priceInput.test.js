import { expect, it } from "vitest";
import { digitInput } from "./iranianFields";
import { formatPrice } from "./formatPrice";
it("round-trips grouped Persian and Arabic prices without losing digits", () => {
  expect(digitInput("۱٬۲۳۴٬۵۶۷")).toBe("1234567");
  expect(digitInput("١٢٣٤")).toBe("1234");
  expect(digitInput(formatPrice(1234567))).toBe("1234567");
});
