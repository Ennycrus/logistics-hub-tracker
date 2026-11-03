"""
Tests for the tracking page address in Settings (used by the Track buttons).

Run with:  python manage.py test core
"""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

URL = '/api/settings/hub/'
GOOD = 'https://example.com/track?waybill={waybill}'


class TrackingUrlTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))

    def save(self, value):
        return self.client.patch(URL, {'tracking_url': value}, format='json')

    def test_starts_empty(self):
        self.assertEqual(self.client.get(URL).json()['tracking_url'], '')

    def test_good_address_is_saved(self):
        self.assertEqual(self.save(GOOD).status_code, 200)
        self.assertEqual(self.client.get(URL).json()['tracking_url'], GOOD)

    def test_address_needs_the_waybill_placeholder(self):
        response = self.save('https://example.com/track')
        self.assertEqual(response.status_code, 400)
        self.assertIn('tracking_url', response.json()['details'])

    def test_only_web_addresses_are_allowed(self):
        self.assertEqual(self.save('javascript:alert(1)//{waybill}').status_code, 400)
        self.assertEqual(self.save('ftp://example.com/{waybill}').status_code, 400)

    def test_can_be_cleared(self):
        self.save(GOOD)
        self.assertEqual(self.save('  ').status_code, 200)
        self.assertEqual(self.client.get(URL).json()['tracking_url'], '')
