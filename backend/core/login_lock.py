"""
The wrong-password lock, for EVERY way of logging in.

After LOGIN_MAX_ATTEMPTS wrong passwords for a username, logging in as that
user is refused for LOGIN_LOCKOUT_MINUTES, even with the right password.

It lives in the authentication backend (settings.AUTHENTICATION_BACKENDS),
which Django uses for every login: the website (/api/auth/login/), the admin
(/admin/) and the browsable API (/api-auth/login/). So no login page can be
used to keep guessing.

The count lives in Django's memory cache, so restarting Django also clears it.
"""

import hashlib

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.cache import cache

from .security_log import log_event


def failures_key(username):
    # A fingerprint of the username, not the username itself: whatever an
    # attacker types (new lines, very long text...), the key stays short and safe.
    digest = hashlib.sha256(username.strip().lower().encode()).hexdigest()
    return f'login-failures:{digest}'


def too_many_failures(username):
    return cache.get(failures_key(username), 0) >= settings.LOGIN_MAX_ATTEMPTS


def record_failure(username):
    """Count one wrong password. The count expires LOGIN_LOCKOUT_MINUTES after the last failure."""
    key = failures_key(username)
    cache.set(key, cache.get(key, 0) + 1, timeout=settings.LOGIN_LOCKOUT_MINUTES * 60)


class LockoutBackend(ModelBackend):
    """Django's normal username/password check, with the wrong-password lock around it."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(get_user_model().USERNAME_FIELD)
        if not username:
            return None
        if too_many_failures(username):
            log_event('LOGIN_BLOCKED', request, user=username)
            return None  # locked: the password is not even checked
        user = super().authenticate(request, username=username, password=password, **kwargs)
        if user is None:
            record_failure(username)
            log_event('LOGIN_FAILED', request, user=username)
            if too_many_failures(username):
                log_event('ACCOUNT_LOCKED', request, user=username)
        else:
            cache.delete(failures_key(username))
            log_event('LOGIN_OK', request, user=username)
        return user