/**
 * One pricing rule for every cart surface (Part S5 follow-up 4, item 3).
 *
 * The API has never exposed a bare `price` on a product: prices live in
 * `price_info` ({price, compare_at_price, discount_percentage, is_on_sale,
 * discount_amount}). Reading `product.price` therefore rendered an empty
 * string (formatPrice(undefined) === "") next to "تومان" and made every
 * guest line total 0 -- the owner's "prices are missing in the guest cart".
 * The same wrong field had been copied into the mini-cart, the search
 * suggestions and the cart page, so the rule now lives here once and all
 * three surfaces call it.
 *
 * Variant lines: a cart line that carries a `variant_id` must be priced
 * from THAT variant's own price_info. Falling back to the product's base
 * price would silently show a wrong number, so a variant line without its
 * variant payload is reported as "not priced yet" (null) instead --
 * callers show "—"/"در حال محاسبه…", never a made-up value.
 *
 * This module only picks WHICH server value to display. It never invents,
 * rounds or recalculates a price; line totals are unit price x quantity,
 * which is the same arithmetic the backend uses for its own line_total.
 */

/** The price_info object that owns a cart line: the variant's when the
 *  line points at a variant, otherwise the product's. */
export function priceInfoForLine(line, product, variant) {
  if (line?.variant_id) return variant?.price_info || null;
  return product?.price_info || null;
}

/** Unit price (Toman) or null when the server value is not loaded. */
export function unitPriceForLine(line, product, variant) {
  const info = priceInfoForLine(line, product, variant);
  return info ? info.price : null;
}

/** Line total = unit price x quantity, or null when the unit is unknown. */
export function lineTotalForLine(line, product, variant) {
  const unit = unitPriceForLine(line, product, variant);
  if (unit === null || unit === undefined) return null;
  return unit * line.quantity;
}

/**
 * Sum of line totals -- returns null when ANY line is still unpriced, so a
 * cart can never advertise a subtotal that quietly ignores a line.
 */
export function sumLineTotals(totals) {
  if (totals.some((total) => total === null || total === undefined)) return null;
  return totals.reduce((sum, total) => sum + total, 0);
}

/** "رنگ: مشکی، اندازه: بزرگ" for a variant payload ("" when there is none). */
export function variantLabel(variant) {
  const values = variant?.attribute_values || [];
  return values.map((av) => `${av.attribute}: ${av.value}`).join("، ");
}
