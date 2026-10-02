"""
Accounts-specific DRF permissions.
"""
from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """
    Object-level permission: the request user must own the object.
    Used alongside IsAuthenticated (which only checks "is someone logged
    in", not "do they own *this* row") on AddressViewSet, so a user can
    never read, update, or delete another user's saved address.
    """

    def has_object_permission(self, request, view, obj):
        return getattr(obj, "user_id", None) == request.user.id
