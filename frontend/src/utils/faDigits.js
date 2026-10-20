/** Display only: never use for identifiers or submitted values. */
export function faDigits(value) {
  return String(value ?? "").replace(/[0-9٠-٩]/g, digit => {
    const code = digit.charCodeAt(0);
    const number = code >= 0x0660 && code <= 0x0669 ? code - 0x0660 : Number(digit);
    return "۰۱۲۳۴۵۶۷۸۹"[number];
  });
}
export function latinDigits(value) {
  return String(value ?? "").replace(/[۰-۹٠-٩]/g, digit => {
    const code = digit.charCodeAt(0);
    return String(code >= 0x06f0 && code <= 0x06f9 ? code - 0x06f0 : code - 0x0660);
  });
}
export function faDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("fa-IR", { year: "numeric", month: "2-digit", day: "2-digit" });
}
export function faDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return `${faDate(date)}، ساعت ${date.toLocaleTimeString("fa-IR", { hour: "numeric", minute: "2-digit" })}`;
}
/**
 * Owner-entered opening / pickup hours.
 *
 * A bare `HH:MM-HH:MM` is a bidi hazard inside an RTL paragraph: the colon
 * and the hyphen carry no direction of their own, so «۱۰:۰۰-۲۱:۰۰» can be
 * read back to front and the range's ends swap sides. Every such range is
 * therefore rewritten as «۱۰:۰۰ تا ۲۱:۰۰» -- Persian digits and the Persian
 * word «تا», which is strongly RTL and pins each end where it belongs.
 *
 * Values that already say «تا», or that are free text («شنبه تا پنجشنبه ۹ تا
 * ۲۱»), keep their shape; only their digits are Persianised.
 */
const HOURS_RANGE = /([۰-۹0-9]{1,2}):([۰-۹0-9]{2})\s*[-–—]\s*([۰-۹0-9]{1,2}):([۰-۹0-9]{2})/g;

export function hoursRange(value) {
  return faDigits(String(value ?? "")).replace(
    HOURS_RANGE,
    (_match, fromHour, fromMinute, toHour, toMinute) =>
      `${fromHour}:${fromMinute} تا ${toHour}:${toMinute}`
  );
}

export function deliveryRange(earliest, latest) {
  if (!earliest) return "";
  const first = faDate(earliest);
  const last = latest ? faDate(latest) : first;
  return first === last ? first : `${first} تا ${last}`;
}
export function deliveryDays(min, max) {
  return min === max ? `تحویل ${faDigits(min)} روزه` : `تحویل ${faDigits(min)} تا ${faDigits(max)} روز کاری`;
}
