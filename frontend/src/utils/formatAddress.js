import { faDigits } from "./faDigits";
import { toAsciiDigits } from "./iranianFields";
/** Accept a saved address or an order's shipping snapshot. */
export function formatAddress(address = {}, prefix = "") {
  const get = key => String(address[`${prefix}${key}`] ?? "").trim();
  const parts = [get("province"), get("city"), get("address")].filter(Boolean);
  if (get("building_number")) parts.push(`پلاک ${get("building_number")}`);
  const unit = get("unit");
  if (unit && !/^0+$/.test(toAsciiDigits(unit))) parts.push(`واحد ${unit}`);
  return faDigits(parts.join("، "));
}
