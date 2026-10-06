"""
Back-in-stock delivery (Part 2) -- same reliability contract as
apps/notifications/services.py: queued with transaction.on_commit (a
rolled-back stock change notifies nobody), provider failures contained
and logged, exactly ONE send per subscription (notified_at stamped on
success; failure keeps the row active for a future restock).
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.notifications.models import NotificationLog
from apps.notifications.providers import get_provider
from apps.notifications.services import mask_phone

logger = logging.getLogger("notifications")

EVENT_BACK_IN_STOCK = "back_in_stock"


def queue_restock_notifications(instance, old_stock: int) -> None:
    """Called from Product.save()/ProductVariant.save() when the row is
    updated. Only the 0 -> N transition matters."""
    if old_stock != 0 or instance.stock_quantity <= 0:
        return
    snapshot = (type(instance).__name__, instance.pk)
    transaction.on_commit(lambda: deliver_restock_notifications(*snapshot))


def deliver_restock_notifications(model_name: str, pk: int) -> None:
    from .models import BackInStockSubscription, Product, ProductVariant

    model = Product if model_name == "Product" else ProductVariant
    obj = model.objects.filter(pk=pk).first()
    if obj is None or obj.stock_quantity <= 0:
        return  # deleted or re-sold-out before commit landed

    subscriptions = BackInStockSubscription.objects.filter(
        notified_at__isnull=True, product_id=obj.pk if model is Product else obj.product_id,
    )
    if model is Product:
        subscriptions = subscriptions.filter(variant__isnull=True)
    else:
        # A variant restock satisfies both variant-level and
        # product-level watchers.
        from django.db.models import Q

        subscriptions = subscriptions.filter(Q(variant=obj) | Q(variant__isnull=True))

    for sub in subscriptions:
        _notify_one(sub, obj)


def _notify_one(sub, obj) -> None:
    product_name = obj.name if hasattr(obj, "name") and type(obj).__name__ == "Product" else obj.product.name
    message = f"«{product_name}» دوباره در کازین گالری موجود شد. سفارش: cusin.ir"
    log = NotificationLog.objects.create(
        event=EVENT_BACK_IN_STOCK,
        channel=NotificationLog.Channel.SMS,
        recipient_masked=mask_phone(sub.phone),
    )
    try:
        message_id = get_provider().send(sub.phone, message=message)
        sub.notified_at = timezone.now()
        sub.save(update_fields=["notified_at", "updated_at"])
        NotificationLog.objects.filter(pk=log.pk).update(
            status=NotificationLog.Status.SENT, provider_message_id=(message_id or "")[:64],
        )
    except Exception as exc:
        NotificationLog.objects.filter(pk=log.pk).update(
            status=NotificationLog.Status.FAILED,
            error=f"{type(exc).__name__}: {exc}"[:2000],
        )
        # Subscription stays ACTIVE: the next 0 -> N restock retries.
        logger.error("Back-in-stock SMS failed for %s: %s", mask_phone(sub.phone), exc)
