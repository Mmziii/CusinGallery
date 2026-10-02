"""
Root-level payment callback alias (Phase 7 - Payment architecture).

Mounts the callback view at /payment/callback/ -- the path shape the
documented PAYMENT_CALLBACK_URL default (https://cusin.ir/payment/callback/)
already uses. The canonical API-side route /api/v1/payments/callback/ in
urls.py runs this exact same view; the alias exists purely so gateway
configuration doesn't have to care which convention the deployment
prefers. Named routes stay on the /api/v1/ side (urls.py) so reverse()
has one unambiguous home.
"""
from django.urls import path

from . import views

urlpatterns = [
    path("payment/callback/", views.PaymentCallbackView.as_view()),
]
