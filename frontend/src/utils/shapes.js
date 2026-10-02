import PropTypes from "prop-types";

/**
 * Shared PropTypes shapes for the API payloads the storefront renders.
 * Mirrors the backend serializers (apps/products/serializers.py) --
 * kept here in one place so product/price rendering components validate
 * their inputs without re-declaring the same structure everywhere.
 */

export const priceInfoShape = PropTypes.shape({
  price: PropTypes.number.isRequired,
  compare_at_price: PropTypes.number,
  discount_percentage: PropTypes.number,
  discount_amount: PropTypes.number,
  is_on_sale: PropTypes.bool,
});

export const productImageShape = PropTypes.shape({
  id: PropTypes.number,
  image: PropTypes.string.isRequired,
  alt_text: PropTypes.string,
  is_primary: PropTypes.bool,
  ordering: PropTypes.number,
});

export const brandShape = PropTypes.shape({
  id: PropTypes.number,
  name: PropTypes.string.isRequired,
  slug: PropTypes.string,
});

export const categoryShape = PropTypes.shape({
  id: PropTypes.number,
  name: PropTypes.string.isRequired,
  slug: PropTypes.string.isRequired,
  image: PropTypes.string,
  ordering: PropTypes.number,
  product_count: PropTypes.number,
  children: PropTypes.array,
});

export const variantShape = PropTypes.shape({
  id: PropTypes.number.isRequired,
  sku: PropTypes.string,
  price_info: priceInfoShape,
  stock_status: PropTypes.string,
  is_in_stock: PropTypes.bool,
  is_active: PropTypes.bool,
  attribute_values: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.number,
      attribute: PropTypes.string.isRequired,
      attribute_slug: PropTypes.string,
      value: PropTypes.string.isRequired,
    })
  ),
  image: productImageShape,
});

/** Shape of ProductListSerializer (catalog rows, cart rows, wishlist). */
export const productShape = PropTypes.shape({
  id: PropTypes.number.isRequired,
  name: PropTypes.string.isRequired,
  slug: PropTypes.string.isRequired,
  sku: PropTypes.string,
  short_description: PropTypes.string,
  primary_image: productImageShape,
  price_info: priceInfoShape,
  stock_status: PropTypes.string,
  is_in_stock: PropTypes.bool,
  brand: brandShape,
  category: categoryShape,
  is_featured: PropTypes.bool,
  is_new: PropTypes.bool,
  is_best_seller: PropTypes.bool,
});

/** Shape of ProductDetailSerializer (single-product page). */
export const productDetailShape = PropTypes.shape({
  ...productShape.shape,
  description: PropTypes.string,
  images: PropTypes.arrayOf(productImageShape),
  variants: PropTypes.arrayOf(variantShape),
  specifications: PropTypes.arrayOf(
    PropTypes.shape({
      attribute: PropTypes.string.isRequired,
      values: PropTypes.arrayOf(PropTypes.string),
    })
  ),
  related_products: PropTypes.arrayOf(productShape),
});

export const bannerShape = PropTypes.shape({
  id: PropTypes.number,
  title: PropTypes.string.isRequired,
  subtitle: PropTypes.string,
  image: PropTypes.string.isRequired,
  cta_text: PropTypes.string,
  cta_url: PropTypes.string,
});

export const dailyDealShape = PropTypes.shape({
  id: PropTypes.number,
  product: productShape.isRequired,
  sale_price: PropTypes.number.isRequired,
  starts_at: PropTypes.string.isRequired,
  ends_at: PropTypes.string.isRequired,
});

export const shippingMethodShape = PropTypes.shape({
  id: PropTypes.string.isRequired,
  cost: PropTypes.number.isRequired,
  free_threshold: PropTypes.number,
  min_days: PropTypes.number.isRequired,
  max_days: PropTypes.number.isRequired,
});
