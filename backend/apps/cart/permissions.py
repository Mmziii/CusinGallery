"""
Cart-specific DRF permissions.

CartItem has no direct `user` field of its own (only `cart`, and `cart`
has `user`) -- apps.accounts.permissions.IsOwner (which checks
`obj.user_id`) doesn't apply directly to it, hence this small
cart-specific version rather than reusing that one incorrectly.
"""
from rest_framework import permissions


class IsCartItemOwner(permissions.BasePermission):
    """
    Object-level permission: the request user must own the cart this
    item belongs to. Defense-in-depth alongside queryset-level scoping
    in the views (see CartItemViewSet.get_queryset) -- same pattern as
    apps.accounts.permissions.IsOwner.
    """

    def has_object_permission(self, request, view, obj):
        return obj.cart.user_id == request.user.id
