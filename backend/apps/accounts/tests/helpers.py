"""
Shared helpers for accounts tests. Not a test module itself (no Test*
classes here -- Django's test runner only collects files/classes it
recognizes as tests, and a bare helper module without those is safely
ignored).
"""
from django.contrib.auth import get_user_model

User = get_user_model()


def make_user(phone="+989120000001", password="a-strong-passw0rd!", **extra):
    """Creates a real, usable customer account the same way registration
    does (create_user, not a raw insert), so tests exercise the same
    password-hashing path as production code."""
    defaults = {
        "username": phone,
        "phone": phone,
        "first_name": "Test",
        "last_name": "User",
    }
    defaults.update(extra)
    return User.objects.create_user(password=password, **defaults)
