import { formatPrice } from "../utils/formatPrice";

/**
 * Renders a price_info object ({price, compare_at_price, is_on_sale, ...})
 * the same way everywhere: current price, struck-through compare-at price
 * when on sale, and a discount badge when the catalog supplies one.
 */
function PriceTag({ priceInfo, size = "md" }) {
  if (!priceInfo) return null;
  const { price, compare_at_price: compareAt, discount_percentage: badge } = priceInfo;

  return (
    <div className={`price price--${size}`}>
      {compareAt ? (
        <span className="price__compare">{formatPrice(compareAt)}</span>
      ) : null}
      <span className="price__current">{formatPrice(price)}</span>
      <span className="price__unit">تومان</span>
      {badge > 0 ? <span className="price__badge">{badge}٪ تخفیف</span> : null}
    </div>
  );
}

export default PriceTag;
