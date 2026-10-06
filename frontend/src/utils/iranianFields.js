/**
 * Part S1 (items 3 + 5): shared client-side rules mirroring the backend
 * address validators (backend/apps/accounts/validators.py). The server
 * stays the authority; these exist to give instant, inline, Persian
 * feedback BEFORE a round-trip and to normalize Persian/Arabic digits
 * as the user types.
 */

const FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const AR_DIGITS = "٠١٢٣٤٥٦٧٨٩";

/** ASCII digits to Persian, for messages shown to the customer. */
export function toPersianDigits(value) {
  return String(value ?? "").replace(/\d/g, (d) => FA_DIGITS[Number(d)]);
}

/** Map Persian/Arabic digits to ASCII; everything else passes through. */
export function toAsciiDigits(value) {
  return String(value ?? "").replace(/[۰-۹٠-٩]/g, (ch) => {
    const fa = FA_DIGITS.indexOf(ch);
    if (fa !== -1) return String(fa);
    const ar = AR_DIGITS.indexOf(ch);
    return ar !== -1 ? String(ar) : ch;
  });
}

/** Normalize an Iranian phone input: ASCII digits, +98/0098 -> 0 form. */
export function normalizePhone(value) {
  let v = toAsciiDigits(value).replace(/[\s-]/g, "");
  if (v.startsWith("+98")) v = `0${v.slice(3)}`;
  else if (v.startsWith("0098")) v = `0${v.slice(4)}`;
  if (v.startsWith("9") && v.length === 10) v = `0${v}`;
  return v;
}

/** Mobile 09xxxxxxxxx or landline 0 + area code (11 digits total). */
export function isValidIranianPhone(value) {
  const v = normalizePhone(value);
  return /^\d{11}$/.test(v) && v.startsWith("0");
}

/** Exactly 10 digits (dashes/spaces tolerated, Persian digits mapped). */
export function isValidPostalCode(value) {
  const v = toAsciiDigits(value).replace(/[\s-]/g, "");
  return /^\d{10}$/.test(v);
}

/** Numeric-field input filter: digits only (Persian -> ASCII on the fly). */
export function digitInput(value) {
  return toAsciiDigits(value).replace(/[^\d]/g, "");
}

/** Part S5 item 6: how long a plot number / unit may be. */
export const MAX_PLOT_UNIT_LENGTH = 20;

/** Normalize a plot/unit input: Persian digits to ASCII, no spaces/dashes. */
export function normalizePlotUnit(value) {
  return toAsciiDigits(value).replace(/[\s-]/g, "");
}

/**
 * Part S5 item 6: the plot number (پلاک) and the unit (واحد) are required
 * and numeric. A customer with no unit enters «۰» -- the helper text says
 * so, and the server enforces the same rule.
 */
export function validatePlotUnit(value, { label, noUnitHint = false }) {
  const cleaned = normalizePlotUnit(value).trim();
  if (!cleaned) {
    return noUnitHint
      ? `${label} را وارد کنید. اگر واحد ندارید عدد ۰ را وارد کنید.`
      : `${label} را وارد کنید.`;
  }
  if (cleaned.length > MAX_PLOT_UNIT_LENGTH) {
    return `${label} حداکثر ${toPersianDigits(MAX_PLOT_UNIT_LENGTH)} رقم می‌تواند باشد.`;
  }
  if (!/^\d+$/.test(cleaned)) return `${label} باید فقط عدد باشد (مثلاً ۱۲).`;
  return "";
}

/**
 * Validate an address-shaped payload (account addresses AND the inline
 * checkout address). Returns { field: message } -- empty object = valid.
 * Messages match the backend's Persian wording closely.
 */
export function validateAddressPayload(
  payload,
  { requirePhone = true, requirePlotAndUnit = true } = {}
) {
  const errors = {};
  const get = (key) => String(payload?.[key] ?? "").trim();

  if (!get("recipient_name")) errors.recipient_name = "نام گیرنده را وارد کنید.";
  if (requirePhone) {
    if (!get("phone")) errors.phone = "شماره تماس را وارد کنید.";
    else if (!isValidIranianPhone(get("phone"))) {
      errors.phone =
        "شماره تماس باید موبایل ایرانی (مانند 09123456789) یا تلفن ثابت با کد شهر (مانند 02112345678) باشد.";
    }
  }
  if (!get("province")) errors.province = "استان را انتخاب کنید.";
  if (!get("city")) errors.city = "شهر را انتخاب کنید.";
  if (!get("address")) errors.address = "آدرس کامل را وارد کنید.";
  if (!get("postal_code")) errors.postal_code = "کد پستی را وارد کنید.";
  else if (!isValidPostalCode(get("postal_code"))) {
    errors.postal_code = "کد پستی باید دقیقاً ۱۰ رقم باشد.";
  }
  // Part S5 item 6: the courier needs the plot number and the unit.
  // Older saved addresses keep working (the server only requires them for
  // NEW addresses and for a one-off checkout address).
  if (requirePlotAndUnit) {
    const buildingError = validatePlotUnit(get("building_number"), { label: "پلاک" });
    if (buildingError) errors.building_number = buildingError;
    const unitError = validatePlotUnit(get("unit"), { label: "واحد", noUnitHint: true });
    if (unitError) errors.unit = unitError;
  }
  return errors;
}
