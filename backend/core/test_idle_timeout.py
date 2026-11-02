"""
Tests for the automatic log-out after a period without activity.

Run with:  python manage.py test core
"""

import datetime

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient


class IdleTimeoutTests(TestCase):

    def setUp(self):
        User.objects.create_user('dammy', password='a-good-password-123')
        self.client = APIClient()
        self.client.post('/api/auth/login/', {'username': 'dammy', 'password': 'a-good-password-123'},
                         format='json')

    def expires_in(self):
        """Seconds until the (only) session expires."""
        return (Session.objects.get().expire_date - timezone.now()).total_seconds()

    def test_session_lasts_the_idle_timeout(self):
        self.assertEqual(settings.IDLE_TIMEOUT_MINUTES, 15)
        self.assertAlmostEqual(self.expires_in(), 15 * 60, delta=5)

    def test_activity_restarts_the_clock(self):
        Session.objects.update(expire_date=timezone.now() + datetime.timedelta(minutes=1))
        self.client.get('/api/shipments/')
        self.assertAlmostEqual(self.expires_in(), 15 * 60, delta=5)

    def test_expired_session_must_log_in_again(self):
        Session.objects.update(expire_date=timezone.now() - datetime.timedelta(seconds=1))
        response = self.client.get('/api/shipments/')
        self.assertEqual(response.status_code, 403)
        self.assertIn('Authentication credentials', response.json()['error'])

    def test_website_is_told_the_timeout(self):
        self.assertEqual(self.client.get('/api/auth/me/').json()['idle_timeout_minutes'], 15)