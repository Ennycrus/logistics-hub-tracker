"""
Tests for logging in from the website.

Run with:  python manage.py test core

enforce_csrf_checks=True makes the test client behave like a real
browser, so these tests prove the CSRF protection is switched on.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient


class AuthApiTests(TestCase):

    def setUp(self):
        User.objects.create_user('dammy', password='a-good-password-123')
        self.client = APIClient(enforce_csrf_checks=True)

    def get_token(self):
        self.client.get('/api/auth/csrf/')
        return self.client.cookies['csrftoken'].value

    def login(self, password='a-good-password-123'):
        return self.client.post(
            '/api/auth/login/', {'username': 'dammy', 'password': password},
            format='json', HTTP_X_CSRFTOKEN=self.get_token(),
        )

    def test_csrf_endpoint_sets_cookie(self):
        self.client.get('/api/auth/csrf/')
        self.assertIn('csrftoken', self.client.cookies)

    def test_me_when_logged_out(self):
        body = self.client.get('/api/auth/me/').json()
        self.assertFalse(body['authenticated'])

    def test_login_and_me(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['username'], 'dammy')

        body = self.client.get('/api/auth/me/').json()
        self.assertTrue(body['authenticated'])

    def test_wrong_password(self):
        response = self.login(password='wrong')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Wrong username or password.')

    def test_login_without_csrf_token_is_refused(self):
        response = self.client.post(
            '/api/auth/login/', {'username': 'dammy', 'password': 'a-good-password-123'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_logged_in_user_can_use_the_api(self):
        self.login()
        self.assertEqual(self.client.get('/api/statuses/').status_code, 200)

    def test_changes_need_csrf_token_after_login(self):
        self.login()
        response = self.client.post('/api/shipments/1/status/', {'status': 1}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_logout(self):
        self.login()
        token = self.client.cookies['csrftoken'].value
        response = self.client.post('/api/auth/logout/', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(self.client.get('/api/auth/me/').json()['authenticated'])