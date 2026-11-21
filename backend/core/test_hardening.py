"""
Tests for the extra protections found by the security check:
  - wrong current passwords on "Change password" count towards the login lock
  - other websites can't use your login, even through a link (SameSite=Strict)

Run with:  python manage.py test core.test_hardening
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

GOOD = 'a-good-password-123'
NEW = 'Hub-Tracker-2026-new'


@override_settings(LOGIN_MAX_ATTEMPTS=5, LOGIN_LOCKOUT_MINUTES=5)
class ChangePasswordGuessingTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('dammy', password=GOOD)
        self.client = APIClient()
        self.client.post('/api/auth/login/', {'username': 'dammy', 'password': GOOD}, format='json')

    def tearDown(self):
        cache.clear()

    def change(self, current):
        return self.client.post('/api/auth/change-password/',
                                {'current_password': current, 'new_password': NEW}, format='json')

    def test_four_wrong_guesses_still_allow_a_change(self):
        for _ in range(4):
            self.assertEqual(self.change('guess').status_code, 400)
        self.assertEqual(self.change(GOOD).status_code, 200)

    def test_fifth_wrong_guess_locks_it(self):
        for _ in range(4):
            self.change('guess')
        self.assertEqual(self.change('guess').status_code, 429)
        self.assertEqual(self.change(GOOD).status_code, 429)  # even the right password
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(GOOD))       # nothing was changed

    def test_guesses_here_also_lock_the_login(self):
        for _ in range(5):
            self.change('guess')
        response = APIClient().post('/api/auth/login/', {'username': 'dammy', 'password': GOOD},
                                    format='json')
        self.assertEqual(response.status_code, 429)


class CookieTests(TestCase):

    def test_login_cookies_are_never_sent_from_other_websites(self):
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, 'Strict')
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, 'Strict')
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)

    def test_login_sets_a_strict_cookie(self):
        User.objects.create_user('dammy', password=GOOD)
        response = APIClient().post('/api/auth/login/', {'username': 'dammy', 'password': GOOD},
                                    format='json')
        self.assertEqual(response.cookies['sessionid']['samesite'], 'Strict')