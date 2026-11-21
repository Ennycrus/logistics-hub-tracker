"""
Tests that the wrong-password lock covers every login page, not only the website's.

Run with:  python manage.py test core.test_login_lock_everywhere
"""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from rest_framework.test import APIClient

GOOD = 'a-good-password-123'


@override_settings(LOGIN_MAX_ATTEMPTS=5, LOGIN_LOCKOUT_MINUTES=5)
class LockEverywhereTests(TestCase):

    def setUp(self):
        cache.clear()
        User.objects.create_superuser('dammy', password=GOOD)

    def tearDown(self):
        cache.clear()

    def admin_login(self, password, page='/admin/login/'):
        """True if the login page logged us in."""
        client = Client()
        client.post(page, {'username': 'dammy', 'password': password, 'next': '/admin/'})
        return '_auth_user_id' in client.session

    def website_login(self, password):
        return APIClient().post('/api/auth/login/', {'username': 'dammy', 'password': password},
                                format='json').status_code

    def test_admin_login_works_normally(self):
        self.assertTrue(self.admin_login(GOOD))

    def test_admin_login_is_locked_after_five_wrong_passwords(self):
        for _ in range(5):
            self.assertFalse(self.admin_login('wrong'))
        self.assertFalse(self.admin_login(GOOD))  # even the right password is refused

    def test_api_auth_login_is_locked_too(self):
        for _ in range(5):
            self.admin_login('wrong', page='/api-auth/login/')
        self.assertFalse(self.admin_login(GOOD, page='/api-auth/login/'))

    def test_guesses_on_the_admin_lock_the_website_too(self):
        for _ in range(5):
            self.admin_login('wrong')
        self.assertEqual(self.website_login(GOOD), 429)

    def test_guesses_on_the_website_lock_the_admin_too(self):
        for _ in range(5):
            self.website_login('wrong')
        self.assertFalse(self.admin_login(GOOD))

    def test_lock_ends_after_the_wait(self):
        for _ in range(5):
            self.admin_login('wrong')
        cache.clear()  # what happens when the 5 minutes pass
        self.assertTrue(self.admin_login(GOOD))