"""Fast deterministic settings for the local test suite (never production)."""
from .development import *  # noqa: F401,F403
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
