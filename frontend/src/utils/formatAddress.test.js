import { expect, it } from "vitest";
import { formatAddress } from "./formatAddress";
const address = { province: "تهران", city: "تهران", address: "خیابان گل", building_number: "12", unit: "3" };
it("includes plate before unit in natural Persian", () => {
 expect(formatAddress(address)).toBe("تهران، تهران، خیابان گل، پلاک ۱۲، واحد ۳");
});
it.each([0,"0","۰","٠","",null,undefined])("omits empty or zero unit %s", unit => {
 expect(formatAddress({...address,unit})).toBe("تهران، تهران، خیابان گل، پلاک ۱۲");
});
it("formats order snapshots identically", () => {
 const order = Object.fromEntries(Object.entries(address).map(([key,value]) => [`shipping_${key}`, value]));
 expect(formatAddress(order,"shipping_")).toBe(formatAddress(address));
});
