"""Admin same-origin framing.

The RelatedObjectLookups "+" buttons open the admin's own popup pages in
an in-page iframe (Task 1). Django's XFrameOptionsMiddleware sends the
global ``X_FRAME_OPTIONS`` -- ``DENY`` in production -- on every response,
so the browser refuses to render ``/admin/...?_popup=1`` inside that
iframe and the modal is blank.

The admin needs to be frameable by *this origin only*: ``SAMEORIGIN`` lets
our own admin page embed our own popup while every other site is still
refused. The storefront and the API keep the global ``DENY``.

Placement matters. This middleware is listed AFTER Django's
``XFrameOptionsMiddleware``, so on the response path it runs BEFORE it
(response middleware runs in reverse); it sets the header, and Django's
middleware then sees a header already present and leaves it alone.

If a Content-Security-Policy with ``frame-ancestors`` ever appears, its
directive is rewritten to ``'self'`` for the admin for exactly the same
reason (a ``'none'`` directive would otherwise override SAMEORIGIN in
modern browsers).
"""
import re

from django.conf import settings

_FRAME_ANCESTORS = re.compile(r"(frame-ancestors\s+)[^;]+", re.IGNORECASE)


class AdminFrameOptionsMiddleware:
    """Allow only this origin to frame pages under the admin path."""

    def __init__(self, get_response):
        self.get_response = get_response
        # Absolute, slash-bounded admin prefix (e.g. "/admin/").
        self.admin_prefix = "/" + settings.ADMIN_PATH.strip("/") + "/"

    def __call__(self, request):
        response = self.get_response(request)
        if request.path_info.startswith(self.admin_prefix):
            response["X-Frame-Options"] = "SAMEORIGIN"
            csp = response.get("Content-Security-Policy")
            if csp and "frame-ancestors" in csp.lower():
                response["Content-Security-Policy"] = _FRAME_ANCESTORS.sub(
                    r"\1'self'", csp
                )
        return response
