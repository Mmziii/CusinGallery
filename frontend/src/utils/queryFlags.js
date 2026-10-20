/**
 * Boolean URL parameters (Task: «مشاهده همه»).
 *
 * The backend boolean filter accepts `1/true/yes` and `0/false/no`
 * (apps/products/filters.py). The storefront must read the SAME spellings
 * so a link, an old bookmark or a hand-typed URL all show the filter as
 * active instead of silently unchecked: «مشاهده همه» used to land on
 * /shop/?on_sale=1 with an unticked «فقط تخفیف‌دار» box.
 */
export const TRUE_PARAM_VALUES = ["1", "true", "yes", "on"];

export function isTruthyParam(value) {
  if (value === true) return true;
  if (value === null || value === undefined) return false;
  return TRUE_PARAM_VALUES.includes(String(value).trim().toLowerCase());
}
