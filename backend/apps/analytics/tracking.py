"""Event recording helpers -- the ONE place that writes analytics.Event rows.

Two callers:
* the storefront's batched endpoint (apps/analytics/views.py) for browser
  events (views, searches, guest cart actions);
* backend code paths that must never lose an event (checkout, payment
  verification, authenticated cart API) -- see apps/orders/services.py,
  apps/payments/services.py and apps/cart/views.py.

Privacy rules enforced here:
* no IP address is ever read or stored;
* the User-Agent is read ONLY to detect bots and is never persisted;
* session keys are sanitised to an opaque ``[A-Za-z0-9_-]`` token.
"""
from __future__ import annotations

import logging
import re
import secrets

from django.utils import timezone

from .models import Event

logger = logging.getLogger(__name__)

#: Cookie the storefront also writes, so server-rendered paths can reuse
#: the same anonymous session even outside an API request.
SESSION_COOKIE = "cusin_sk"
#: Header the storefront's axios client attaches to every API call.
SESSION_HEADER = "X-Cusin-Session"

SESSION_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

#: Substrings that identify a crawler/monitor rather than a shopper. Only
#: ever tested against the request header -- never stored.
BOT_TOKENS = (
    "bot", "crawler", "crawl", "spider", "slurp", "bingpreview",
    "headless", "phantomjs", "selenium", "puppeteer", "playwright",
    "python-requests", "python-urllib", "aiohttp", "httpx", "curl/", "wget",
    "facebookexternalhit", "whatsapp", "telegrambot", "semrush", "ahrefs",
    "uptime", "pingdom", "monitor", "lighthouse",
)

#: Hard caps that keep a single request small.
MAX_BATCH_SIZE = 25
MAX_SEARCH_QUERY = 200

VALID_TYPES = frozenset(Event.Type.values)


def is_bot(user_agent: str | None) -> bool:
    """True for obvious crawlers/monitors. The header is not stored."""
    ua = (user_agent or "").lower()
    if not ua:
        return False
    return any(token in ua for token in BOT_TOKENS)


def clean_session_key(value) -> str:
    """Return a safe anonymous session key, or "" when it is not one."""
    key = str(value or "").strip()
    return key if SESSION_KEY_RE.match(key) else ""


def session_key_from_request(request) -> str:
    """The anonymous session key sent by the browser (header, then cookie).

    ``request`` may be a DRF request or a plain Django request; the plain
    one is used so server-rendered paths work too. No IP is involved.
    """
    plain = getattr(request, "_request", request)
    key = clean_session_key(plain.headers.get(SESSION_HEADER))
    if not key:
        key = clean_session_key(plain.COOKIES.get(SESSION_COOKIE))
    return key


def new_session_key() -> str:
    """Server-side fallback for tests/tools that need a valid random key."""
    return secrets.token_urlsafe(18)[:32]


def _fallback_session_key(user) -> str:
    """Events without a browser key still belong to a session.

    For a logged-in user ``u:<pk>`` is anonymous enough to count as one
    session, and it keeps the conversion rate meaningful when a client
    (e.g. an old browser, a curl script, a test) omits the random key.
    """
    if user is not None and getattr(user, "pk", None):
        return f"u:{user.pk}"
    return ""


def record_event(
    event_type: str,
    *,
    product=None,
    order=None,
    user=None,
    session_key: str = "",
    search_query: str = "",
    search_results=None,
    province: str = "",
    city: str = "",
    created_at=None,
):
    """Write one event. NEVER raises -- tracking must not break a page.

    Returns the created Event, or None when the input was unusable (an
    unknown type) or the write failed. Callers that care (tests) can
    inspect the database; production code simply carries on.
    """
    if event_type not in VALID_TYPES:
        return None

    key = clean_session_key(session_key) or _fallback_session_key(user)

    # Order events carry the province/city known from the order snapshot.
    if order is not None:
        province = province or getattr(order, "shipping_province", "") or ""
        city = city or getattr(order, "shipping_city", "") or ""
        if user is None and getattr(order, "user_id", None):
            user = order.user

    if search_results is not None:
        try:
            search_results = max(0, int(search_results))
        except (TypeError, ValueError):
            search_results = None

    try:
        return Event.objects.create(
            event_type=event_type,
            product=product,
            order=order,
            user=user if getattr(user, "pk", None) else None,
            session_key=key,
            search_query=(search_query or "").strip()[:MAX_SEARCH_QUERY],
            search_results=search_results,
            province=(province or "")[:100],
            city=(city or "")[:100],
            created_at=created_at or timezone.now(),
        )
    except Exception:  # noqa: BLE001 - analytics must never break a request
        logger.exception("analytics: could not record %s event", event_type)
        return None
