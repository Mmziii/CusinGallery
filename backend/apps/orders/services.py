"""
Checkout / order business logic (Phase 6; coupon application added with
the discounts work).

Kept separate from views.py, mirroring the apps.cart.services pattern
established in Phase 5 -- validation and persistence logic here, thin
HTTP orchestration in views.py.

Still OUT of scope here, per the master spec's payment flow (section
26-27, which shows "Reduce Inventory" happening *after* "Mark Payment As
Paid"):
    - No stock decrement happens here. Checkout re-validates that
      current stock is sufficient (the same check apps.cart.services
      already performs for the cart itself), but does not reserve or
      subtract it. That happens only when payment is confirmed (see
      apps.payments.services + apps.orders.inventory).
    - No payment gateway interaction of any kind. Every order created
      here starts at Order.Status.PENDING / Order.PaymentStatus.UNPAID
      and stays there until payment changes it.

Coupon application IS done here: the client supplies only a code, and
apps.discounts.services computes validity + the exact Toman discount
server-side. The CouponUsage row, however, is written at payment success
(not here) so an abandoned unpaid order never burns a coupon's quota --
see apps.payments.services._record_coupon_usage.
"""
from django.db import transaction

from apps.accounts.models import Address
from apps.cart import services as cart_services
from apps.discounts import services as discount_services

from . import shipping
from .models import Order, OrderItem


class CheckoutError(Exception):
    """
    Raised for any checkout business-rule violation. Carries a dict
    shaped like a DRF serializer error (field -> [messages]), same
    convention as apps.cart.services.CartError, so views can translate
    it directly into a 400 response.
    """

    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


def _apply_coupon(user, coupon_code, cart_view):
    """
    Validates the coupon and returns (coupon, discount_amount). Runs a
    row-lock on the Coupon for the duration of the surrounding checkout
    transaction so two concurrent checkouts can't both pass the last
    remaining use -- the usage counts they're checked against can't
    change until this transaction commits.

    CouponError (any rule violation) is translated into a CheckoutError
    so the API surfaces it as a normal 400 with the coupon_code field.
    """
    from apps.discounts.models import Coupon

    try:
        with transaction.atomic():
            # Locks the coupon row for the rest of the checkout
            # transaction; validate_and_calculate below re-reads the same
            # row, now under this lock. The fetched object is discarded
            # immediately -- the point is purely the serialization.
            Coupon.objects.select_for_update().filter(code__iexact=coupon_code).first()
            evaluation = discount_services.validate_and_calculate(user, coupon_code, cart_view)
            return evaluation.coupon, evaluation.discount_amount
    except discount_services.CouponError as exc:
        raise CheckoutError(exc.errors)


def _resolve_shipping_fields(user, validated_data):
    """
    Returns the flat shipping_* fields Order expects, either copied from
    one of the user's own saved Address rows, or taken directly from
    inline fields in the checkout request -- see
    apps.orders.serializers.CheckoutSerializer for which of the two
    shapes a given request used and how that's validated before this is
    ever called.

    Ownership is enforced here, not just at the serializer level: the
    Address lookup is filtered by `user=user`, so a client cannot use
    checkout to snapshot another user's saved address by guessing its
    id -- it simply won't be found (404-equivalent CheckoutError), the
    same "doesn't exist from this user's point of view" pattern used
    throughout this project (e.g. apps.accounts.views.AddressViewSet).
    """
    from . import shipping

    method = validated_data.get("shipping_method") or shipping.DEFAULT_METHOD
    if not shipping.get_shipping_methods()[method].get("requires_address", True):
        # Pickup (Part 1): the snapshot carries WHO collects the order;
        # there is no delivery address to store.
        return {
            "shipping_recipient_name": validated_data["recipient_name"],
            "shipping_phone": validated_data["phone"],
            "shipping_province": "",
            "shipping_city": "",
            "shipping_address": "",
            "shipping_postal_code": "",
            "shipping_unit": "",
            "shipping_building_number": "",
        }

    address_id = validated_data.get("address_id")

    if address_id is not None:
        try:
            address = Address.objects.get(pk=address_id, user=user)
        except Address.DoesNotExist:
            raise CheckoutError({"address_id": ["This address does not exist."]})
        return {
            "shipping_recipient_name": address.recipient_name,
            "shipping_phone": address.phone,
            "shipping_province": address.province,
            "shipping_city": address.city,
            "shipping_address": address.address,
            "shipping_postal_code": address.postal_code,
            "shipping_unit": address.unit,
            "shipping_building_number": address.building_number,
        }

    return {
        "shipping_recipient_name": validated_data["recipient_name"],
        "shipping_phone": validated_data["phone"],
        "shipping_province": validated_data["province"],
        "shipping_city": validated_data["city"],
        "shipping_address": validated_data["address"],
        "shipping_postal_code": validated_data["postal_code"],
        "shipping_unit": validated_data.get("unit", ""),
        "shipping_building_number": validated_data.get("building_number", ""),
    }


def checkout(user, validated_data) -> Order:
    """
    Converts the user's current cart into a real Order + OrderItems.

    Server-authoritative by construction, not by convention: the input
    (`validated_data`, from CheckoutSerializer) contains only an address
    selection -- no price, no quantity, no total of any kind ever comes
    from the client. Every monetary value written to the Order below is
    computed here, fresh, from apps.cart.services.build_cart_view()
    (which itself reuses apps.products.pricing -- the same mechanism the
    public catalog API uses), never trusted from anywhere else.
    """
    # Address resolution doesn't need the cart lock below -- kept outside
    # the atomic block to keep the lock's hold time minimal.
    shipping_fields = _resolve_shipping_fields(user, validated_data)

    with transaction.atomic():
        cart = cart_services.get_or_create_cart(user)

        # Locks the cart's item rows for the rest of this transaction so
        # a second, concurrent checkout attempt for the same cart (e.g.
        # a double-submit from an impatient click) blocks until this one
        # finishes, then sees an empty cart -- rather than both
        # succeeding and creating two orders from the same cart
        # contents. The immediate result is discarded; build_cart_view's
        # own (unlocked) query re-reads the same now-locked rows next --
        # Postgres row locks apply for the rest of the transaction
        # regardless of which specific query touches the row afterward,
        # so this is not a redundant no-op.
        list(cart.items.select_for_update())

        cart_view = cart_services.build_cart_view(cart)
        lines = cart_view["lines"]

        if not lines:
            raise CheckoutError({"cart": ["Your cart is empty."]})

        unavailable = [line for line in lines if not line.is_available]
        if unavailable:
            raise CheckoutError(
                {
                    "cart": [
                        f"'{line.item.product.name}' is no longer available in the requested "
                        f"quantity. Please update your cart before checking out."
                        for line in unavailable
                    ]
                }
            )

        subtotal = cart_view["subtotal"]

        # Shipping: the client only picks a configured method (validated
        # by CheckoutSerializer.validate_shipping_method); its cost and
        # delivery window are computed here, server-side, from the
        # settings in force RIGHT NOW -- then snapshotted onto the Order
        # so they never change afterwards.
        shipping_method = validated_data.get("shipping_method") or shipping.DEFAULT_METHOD
        shipping_cost = shipping.calculate_shipping_cost(subtotal, shipping_method)
        delivery_min, delivery_max = shipping.calculate_estimated_delivery(shipping_method)

        coupon = None
        discount_amount = 0
        coupon_code = (validated_data.get("coupon_code") or "").strip()
        if coupon_code:
            coupon, discount_amount = _apply_coupon(user, coupon_code, cart_view)

        total = subtotal + shipping_cost - discount_amount

        order = Order.objects.create(
            user=user,
            subtotal=subtotal,
            discount_amount=discount_amount,
            shipping_cost=shipping_cost,
            total=total,
            coupon=coupon,
            shipping_method=shipping_method,
            estimated_delivery_min=delivery_min,
            estimated_delivery_max=delivery_max,
            **shipping_fields,
        )

        order_items = [
            OrderItem(
                order=order,
                product=line.item.product,
                variant=line.item.variant,
                product_name=line.item.product.name,
                sku=line.item.variant.sku if line.item.variant_id else line.item.product.sku,
                unit_price=line.price_info.price,
                quantity=line.item.quantity,
                total_price=line.line_total,
            )
            for line in lines
        ]
        # bulk_create (skips full_clean()/save()) is safe here -- unlike
        # apps.cart.services.add_item, which validates less-trusted
        # client-adjacent input, every field above is derived from
        # already-valid, system-computed data (a real CartItem's own
        # quantity, the product's own name/sku, and PriceInfo's own
        # price), not something a malformed request could corrupt.
        OrderItem.objects.bulk_create(order_items)

        # The cart's contents have now been captured as a real order --
        # empty it, same as a successful purchase would in any real
        # store. Reuses apps.cart.services.clear_cart rather than a
        # second `cart.items.all().delete()` written here.
        cart_services.clear_cart(cart)

    return order
