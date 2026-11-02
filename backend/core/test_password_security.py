"""
Tests for the wrong-password limit and changing your password.

Run with:  python manage.py test core
"""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

GOOD = 'a-good-password-123'


@override_settings(LOGIN_MAX_ATTEMPTS=5, LOGIN_LOCKOUT_MINUTES=5)
class LoginLimitTests(TestCase):

    def setUp(self):
        cache.clear()
        User.objects.create_user('dammy', password=GOOD)
        self.client = APIClient()

    def tearDown(self):
        cache.clear()  # never leave a lock behind for other tests

    def login(self, password, username='dammy'):
        return self.client.post('/api/auth/login/', {'username': username, 'password': password},
                                format='json')

    def test_four_wrong_passwords_still_allow_login(self):
        for _ in range(4):
            self.assertEqual(self.login('wrong').status_code, 400)
        self.assertEqual(self.login(GOOD).status_code, 200)

    def test_fifth_wrong_password_locks_the_account(self):
        for _ in range(4):
            self.login('wrong')
        response = self.login('wrong')
        self.assertEqual(response.status_code, 429)
        self.assertIn('Too many wrong passwords', response.json()['error'])

    def test_locked_account_refuses_even_the_right_password(self):
        for _ in range(5):
            self.login('wrong')
        self.assertEqual(self.login(GOOD).status_code, 429)

    def test_lock_ends_after_the_wait(self):
        for _ in range(5):
            self.login('wrong')
        cache.clear()  # what happens when the 5 minutes pass
        self.assertEqual(self.login(GOOD).status_code, 200)

    def test_correct_login_resets_the_count(self):
        for _ in range(4):
            self.login('wrong')
        self.login(GOOD)
        self.client.post('/api/auth/logout/')
        for _ in range(4):
            self.assertEqual(self.login('wrong').status_code, 400)  # counting starts again

    def test_username_case_does_not_bypass_the_lock(self):
        for _ in range(5):
            self.login('wrong')
        self.assertEqual(self.login(GOOD, username='DAMMY').status_code, 429)


class ChangePasswordTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('dammy', password=GOOD)
        self.client = APIClient()
        self.client.post('/api/auth/login/', {'username': 'dammy', 'password': GOOD}, format='json')

    def change(self, current, new):
        return self.client.post('/api/auth/change-password/',
                                {'current_password': current, 'new_password': new}, format='json')

    def test_password_is_changed_and_you_stay_logged_in(self):
        response = self.change(GOOD, 'Hub-Tracker-2026-new')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Hub-Tracker-2026-new'))
        self.assertTrue(self.client.get('/api/auth/me/').json()['authenticated'])

    def test_wrong_current_password_is_refused(self):
        response = self.change('not-my-password', 'Hub-Tracker-2026-new')
        self.assertEqual(response.status_code, 400)
        self.assertIn('current_password', response.json()['details'])

    def test_weak_new_password_is_refused(self):
        response = self.change(GOOD, '12345678')
        self.assertEqual(response.status_code, 400)
        self.assertIn('new_password', response.json()['details'])

    def test_same_password_is_refused(self):
        self.assertEqual(self.change(GOOD, GOOD).status_code, 400)

    def test_must_be_logged_in(self):
        self.client.post('/api/auth/logout/')
        self.assertEqual(self.change(GOOD, 'Hub-Tracker-2026-new').status_code, 403)