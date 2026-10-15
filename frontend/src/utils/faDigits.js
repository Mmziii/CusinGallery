/** Display only: never use for identifiers or submitted values. */
export function faDigits(value) {
  return String(value ?? "").replace(/\d/g, digit => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);
}
export function faDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return `${date.toLocaleDateString("fa-IR")}، ساعت ${date.toLocaleTimeString("fa-IR", { hour: "numeric", minute: "2-digit" })}`;
}
export function deliveryRange(earliest, latest) {
  if (!earliest) return "";
  const first = new Date(earliest).toLocaleDateString("fa-IR");
  const last = latest ? new Date(latest).toLocaleDateString("fa-IR") : first;
  return first === last ? first : `${first} تا ${last}`;
}
export function deliveryDays(min, max) {
  return min === max ? `تحویل ${faDigits(min)} روزه` : `تحویل ${faDigits(min)} تا ${faDigits(max)} روز کاری`;
}
