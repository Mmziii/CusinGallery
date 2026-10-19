"""Batched, fire-and-forget storefront tracking endpoint.

``POST /api/v1/analytics/events/``

Body::

    {
      "session_key": "<anonymous random key>",
      "events": [
        {"type": "product_view", "product_id": 12},
        {"type": "search", "query": "کتری", "results": 4},
        ...
      ]
    }

Guarantees (see the tests):
* anonymous + CSRF-free by design, because the storefront must be able
  to send events even before a CSRF cookie exists. A logged-in shopper is
  still identified from the session through a SessionAuthentication
  subclass whose ``enforce_csrf`` is a deliberate no-op -- the endpoint
  appends non-sensitive rows and never returns anything but a count;
* bots are ignored (the User-Agent is tested, never stored);
* four independent fixed-window limits -- per session key, per (hashed)
  client address, per endpoint and per new session key minted by one
  address per hour -- so rotating the browser-chosen key cannot buy extra
  quota. Over any limit the answer is still 202 with
  ``{"accepted": 0, "ignored": "rate-limited"}`` and nothing is stored;
* invalid/unknown entries are skipped, never a 400 that could surface in
  the UI;
* the response is always tiny and the client never waits on it.
"""
from __future__ import annotations

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.products.models import Product

from .models import Event
from .ratelimit import RATE_LIMITED, check_batch, client_ip
from .tracking import (
    MAX_BATCH_SIZE,
    MAX_SEARCH_QUERY,
    clean_session_key,
    is_bot,
    record_event,
    session_key_from_request,
)

def _product_for(raw_product_id):
    try:
        product_id = int(raw_product_id)
    except (TypeError, ValueError):
        return None
    if product_id <= 0:
        return None
    return Product.objects.filter(pk=product_id).first()


def _clean_type(value) -> str:
    return str(value or "").strip().lower()


class _TrackOnlySessionAuthentication(SessionAuthentication):
    """Identify a logged-in shopper WITHOUT requiring a CSRF token.

    A fire-and-forget beacon must never fail because the page happens to
    have no csrftoken cookie yet (first visit) or because the browser is
    restoring a tab. The endpoint only appends non-sensitive analytics
    rows, is rate limited per anonymous session, and never exposes
    anything back -- so CSRF protection would buy nothing here while
    costing real events. The ``X-Cusin-Session`` key, not the CSRF
    token, is what reports depend on.
    """

    def enforce_csrf(self, request):  # noqa: ARG002 - deliberate no-op
        return


class EventBatchView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = [_TrackOnlySessionAuthentication]

    def post(self, request):
        plain = getattr(request, "_request", request)
        if is_bot(plain.headers.get("User-Agent")):
            return Response({"accepted": 0, "ignored": "bot"}, status=status.HTTP_202_ACCEPTED)

        payload = request.data if isinstance(request.data, dict) else {}
        session_key = (
            session_key_from_request(request)
            or clean_session_key(payload.get("session_key"))
        )

        # Every request is counted, keyless ones included: an empty (or
        # rotated) key must not be a free pass. The address is hashed and
        # used only in cache keys -- see apps/analytics/ratelimit.py.
        if check_batch(session_key=session_key, ip=client_ip(plain)):
            return Response(
                {"accepted": 0, "ignored": RATE_LIMITED},
                status=status.HTTP_202_ACCEPTED,
            )

        if not session_key:
            # No anonymous key => nothing to attribute the batch to. Silently
            # accept (the storefront must never see an error) and store nothing.
            return Response({"accepted": 0, "ignored": "no-session"}, status=status.HTTP_202_ACCEPTED)

        raw_events = payload.get("events")
        if not isinstance(raw_events, list):
            return Response(
                {"events": ["فهرست رویدادها الزامی است."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        raw_events = raw_events[: int(getattr(settings, "ANALYTICS_MAX_BATCH", MAX_BATCH_SIZE) or MAX_BATCH_SIZE)]

        django_user = getattr(request, "user", None)
        user = django_user if getattr(django_user, "is_authenticated", False) else None

        accepted = 0
        for raw in raw_events:
            if not isinstance(raw, dict):
                continue
            event_type = _clean_type(raw.get("type"))
            if event_type not in Event.Type.values:
                continue

            product = None
            if raw.get("product_id") not in (None, "", 0, "0"):
                product = _product_for(raw.get("product_id"))

            query = str(raw.get("query") or "").strip()[:MAX_SEARCH_QUERY]
            results = raw.get("results")
            if event_type == Event.Type.SEARCH and not query:
                continue

            event = record_event(
                event_type,
                product=product,
                user=user,
                session_key=session_key,
                search_query=query,
                search_results=results if event_type == Event.Type.SEARCH else None,
            )
            if event is not None:
                accepted += 1

        return Response({"accepted": accepted}, status=status.HTTP_202_ACCEPTED)
