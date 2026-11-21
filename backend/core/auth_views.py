"""
Login for the React website, using Django's normal session login.

How it works:
  1. React calls GET /api/auth/csrf/ once. Django sets a "csrftoken" cookie.
  2. React logs in with POST /api/auth/login/, sending that token in the
     X-CSRFToken header. Django sets a "sessionid" cookie.
  3. The browser sends the session cookie with every later request, so the
     API knows it's you. Changes (POST/PATCH) also send the CSRF token.

The CSRF token proves a request really came from your own page,
not from another website trying to act as you.

After IDLE_TIMEOUT_MINUTES (settings.py) without any request, the session
expires and you must log in again.

Wrong passwords: after LOGIN_MAX_ATTEMPTS failures for a username, logging in
as that user is refused for LOGIN_LOCKOUT_MINUTES (even with the right password).
The lock itself is in core/login_lock.py, so it also covers the admin login.
Every login, logout and password change is written to the security log.
"""

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .login_lock import record_failure, too_many_failures
from .security_log import log_event


def user_data(user):
    timeout = settings.IDLE_TIMEOUT_MINUTES
    if not user.is_authenticated:
        return {'authenticated': False, 'username': None, 'idle_timeout_minutes': timeout}
    return {'authenticated': True, 'username': user.get_username(), 'idle_timeout_minutes': timeout}


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


def locked_response():
    minutes = settings.LOGIN_LOCKOUT_MINUTES
    return Response(
        {'error': f'Too many wrong passwords. Wait {minutes} minutes, then try again.', 'details': {}},
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CsrfView(APIView):
    """GET /api/auth/csrf/ -> sets the csrftoken cookie."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'detail': 'CSRF cookie set.'})


class MeView(APIView):
    """GET /api/auth/me/ -> who is logged in (or that nobody is)."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(user_data(request.user))


@method_decorator(csrf_protect, name='dispatch')
class LoginView(APIView):
    """POST /api/auth/login/  {"username": "...", "password": "..."}"""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data['username']

        # Checked BEFORE the password, so a locked account can't be guessed at all.
        if too_many_failures(username):
            log_event('LOGIN_BLOCKED', request, user=username)
            return locked_response()

        user = authenticate(request, **serializer.validated_data)  # counts a wrong password itself
        if user is None:
            if too_many_failures(username):
                return locked_response()
            return Response(
                {'error': 'Wrong username or password.', 'details': {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, user)
        return Response(user_data(user))


class LogoutView(APIView):
    """POST /api/auth/logout/"""

    permission_classes = [AllowAny]

    def post(self, request):
        if request.user.is_authenticated:
            log_event('LOGOUT', request, user=request.user.get_username())
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField()
    new_password = serializers.CharField()


class ChangePasswordView(APIView):
    """
    POST /api/auth/change-password/  {"current_password": "...", "new_password": "..."}

    You must be logged in and know your current password. The new password must
    pass Django's password rules (length, not too common, not all numbers, not
    like your username). You stay logged in afterwards.

    Wrong current passwords count towards the same lock as the login pages, so
    someone at your unlocked laptop can't use this form to guess your password.
    """

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user
        username = user.get_username()

        if too_many_failures(username):
            log_event('PASSWORD_CHANGE_BLOCKED', request, user=username)
            return locked_response()
        if not user.check_password(data['current_password']):
            record_failure(username)
            log_event('PASSWORD_CHANGE_FAILED', request, user=username)
            if too_many_failures(username):
                log_event('ACCOUNT_LOCKED', request, user=username)
                return locked_response()
            raise ValidationError({'current_password': ['Your current password is wrong.']})
        if data['new_password'] == data['current_password']:
            raise ValidationError({'new_password': ['Choose a password different from the current one.']})
        try:
            validate_password(data['new_password'], user)
        except ValidationError as error:
            raise ValidationError({'new_password': error.messages})

        user.set_password(data['new_password'])
        user.save()
        update_session_auth_hash(request, user)  # keep this login session valid
        log_event('PASSWORD_CHANGED', request, user=username)
        return Response({'detail': 'Password changed.'})