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
"""

from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


def user_data(user):
    if not user.is_authenticated:
        return {'authenticated': False, 'username': None}
    return {'authenticated': True, 'username': user.get_username()}


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


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

        user = authenticate(request, **serializer.validated_data)
        if user is None:
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
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)