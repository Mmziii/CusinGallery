"""Fixed-window abuse limits for the batched storefront tracking endpoint.

The anonymous ``session_key`` is chosen by the browser, so a limit keyed on
it alone is trivially bypassed by rotating the key on every request. Four
independent counters therefore share the work:

``global``
    The whole endpoint, per minute. A safety net for a distributed flood.
``ip``
    The client's address, per minute. This is what makes key rotation
    pointless: the attacker's address stays the same (or, behind a proxy,
    the address the trusted proxy reports).
``session``
    The anonymous browser key, per minute -- the original limit.
``keys``
    How many DISTINCT session keys one address may mint per hour, which
    also stops a script that stays under the per-minute limit.

Privacy: the address is read from the request (``REMOTE_ADDR``, or the
last hop of ``X-Forwarded-For`` behind a declared trusted proxy), reduced
to a salted HMAC and used **only inside cache keys**. It is never stored in
the database, never logged and never returned -- ``Event`` has no IP field
at all (see test_rate_limits). The cache entries themselves expire within
minutes.
"""
from __future__ import annotations

import time

from django.conf import settings
from django.core.cache import cache
from django.utils.crypto import salted_hmac

WINDOW_SECONDS = 60
HOUR_SECONDS = 3600

GLOBAL_RATE_DEFAULT = 3000
IP_RATE_DEFAULT = 120
SESSION_RATE_DEFAULT = 60
SESSION_KEYS_PER_HOUR_DEFAULT = 100

#: Value of the ``ignored`` field in the always-202 response. The storefront
#: treats every response the same; only tests and ops read this.
RATE_LIMITED = "rate-limited"


def _limit(name: str, default: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default
    return max(1, value)


def client_ip(request) -> str:
    """The client address, honouring ``X-Forwarded-For`` only if configured.

    ``ANALYTICS_TRUSTED_PROXY_COUNT`` is the number of reverse proxies in
    front of Django (production: one nginx). With n trusted proxies the
    client is the n-th entry from the RIGHT: nginx appends the peer it saw
    (``$proxy_add_x_forwarded_for``), so anything a client prepends is
    untrusted decoration and cannot be used to rotate the counter.
    """
    plain = getattr(request, "_request", request)
    hops = int(getattr(settings, "ANALYTICS_TRUSTED_PROXY_COUNT", 0) or 0)
    meta = getattr(plain, "META", {}) or {}

    if hops > 0:
        forwarded = [
            part.strip()
            for part in str(meta.get("HTTP_X_FORWARDED_FOR", "")).split(",")
            if part.strip()
        ]
        if len(forwarded) >= hops:
            return forwarded[-hops]
        real = str(meta.get("HTTP_X_REAL_IP", "")).strip()
        if real:
            return real
    return str(meta.get("REMOTE_ADDR", "")).strip()


def fingerprint_ip(ip: str) -> str:
    """Salted, non-reversible identity used in cache keys (never stored)."""
    return salted_hmac(
        "analytics.rate-limit.ip", ip or "unknown", algorithm="sha256",
    ).hexdigest()


def _hit(key: str, ttl: int) -> int:
    """Increment a fixed-window counter and return the new value."""
    cache.add(key, 0, ttl)
    try:
        return cache.incr(key)
    except ValueError:  # pragma: no cover - key expired between add and incr
        cache.set(key, 1, ttl)
        return 1


def _count_distinct_session(ip_fingerprint: str, session_key: str, hour: int, limit: int) -> bool:
    """True while this address stays under its hourly NEW-session budget."""
    marker = f"analytics:sk:{hour}:{ip_fingerprint}:{session_key}"
    if not cache.add(marker, 1, HOUR_SECONDS):
        return True  # already counted this hour
    counter = f"analytics:skc:{hour}:{ip_fingerprint}"
    cache.add(counter, 0, HOUR_SECONDS)
    try:
        count = cache.incr(counter)
    except ValueError:  # pragma: no cover - key expired between add and incr
        cache.set(counter, 1, HOUR_SECONDS)
        count = 1
    return count <= limit


def check_batch(*, session_key: str, ip: str) -> str:
    """Count one batch; return "" when it may be stored, else a short reason.

    The caller answers every reason with the same 202 + ``accepted: 0`` +
    ``ignored: "rate-limited"`` body, so the storefront never sees a change
    between a bot, a throttle and a malformed batch.
    """
    now = int(time.time())
    minute = now // WINDOW_SECONDS
    ttl = WINDOW_SECONDS * 2
    ip_fp = fingerprint_ip(ip)

    if _hit(f"analytics:rl:global:{minute}", ttl) > _limit(
        "ANALYTICS_GLOBAL_RATE_LIMIT_PER_MINUTE", GLOBAL_RATE_DEFAULT
    ):
        return "global"

    if _hit(f"analytics:rl:ip:{ip_fp}:{minute}", ttl) > _limit(
        "ANALYTICS_IP_RATE_LIMIT_PER_MINUTE", IP_RATE_DEFAULT
    ):
        return "ip"

    if not session_key:
        return ""  # nothing will be stored; the address was still counted

    if _hit(f"analytics:rl:sk:{session_key}:{minute}", ttl) > _limit(
        "ANALYTICS_RATE_LIMIT_PER_MINUTE", SESSION_RATE_DEFAULT
    ):
        return "session"

    if not _count_distinct_session(
        ip_fp,
        session_key,
        now // HOUR_SECONDS,
        _limit("ANALYTICS_SESSION_KEYS_PER_IP_PER_HOUR", SESSION_KEYS_PER_HOUR_DEFAULT),
    ):
        return "keys"

    return ""
