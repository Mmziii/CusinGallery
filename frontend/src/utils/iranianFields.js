/**
 * Part S1 (items 3 + 5): shared client-side rules mirroring the backend
 * address validators (backend/apps/accounts/validators.py). The server
 * stays the authority; these exist to give instant, inline, Persian
 * feedback BEFORE a round-trip and to normalize Persian/Arabic digits
 * as the user types.
 */

const FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const AR_DIGITS = "٠١٢٣٤٥٦٧٨٩";

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

/**
 * Validate an address-shaped payload (account addresses AND the inline
 * checkout address). Returns { field: message } -- empty object = valid.
 * Messages match the backend's Persian wording closely.
 */
export function validateAddressPayload(payload, { requirePhone = true } = {}) {
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
  return errors;
}
