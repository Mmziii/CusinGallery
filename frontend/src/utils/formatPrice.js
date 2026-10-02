/**
 * Formats an integer/decimal Toman amount using Persian digit grouping.
 * Kept here (rather than inline in components) so every price display
 * in the app -- product cards, cart, checkout, orders -- stays consistent
 * once those UIs are built.
 */
export function formatPrice(amount) {
  if (amount === null || amount === undefined || Number.isNaN(Number(amount))) {
    return "";
  }
  return new Intl.NumberFormat("fa-IR").format(Number(amount));
}
