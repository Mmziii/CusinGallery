"""
Review business logic.

The only rule here that can't be expressed as a serializer field:
is_verified_purchase. It is COMPUTED -- from whether the reviewing user
has a PAID order containing the product -- never accepted from the
client, per the model's own help_text ("Set by ... order-completion
logic, not editable data entry"). A review can also BECOME verified
later (if it was written before the order was paid), so the check runs
on edit as well.

"Completed order" means payment_status == PAID: a pending/failed payment
proves nothing about ownership of the product.
"""
from django.db.models import Q

from apps.orders.models import Order, OrderItem


def has_verified_purchase(user, product) -> bool:
    if not user.is_authenticated:
        return False
    return (
        OrderItem.objects.filter(
            order__user=user,
            order__payment_status=Order.PaymentStatus.PAID,
        )
        .filter(Q(product=product) | Q(variant__product=product))
        .exists()
    )
