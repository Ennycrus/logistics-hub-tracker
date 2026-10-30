"""
Tests for the Settings API.

Run with:  python manage.py test core
"""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from shipments.services.status_service import create_shipment

from .models import FailureReason, HubConfig, StatusOption


class SettingsApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        self.unchecked = StatusOption.objects.get(name='Not Yet Checked')
        self.pending = StatusOption.objects.get(name='Pending Delivery')

    # --- Hub ----------------------------------------------------------------

    def test_hub_settings_read_and_update(self):
        response = self.client.patch('/api/settings/hub/', {'hub_name': ' Akala_Express '}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(HubConfig.get().hub_name, 'Akala_Express')
        self.assertEqual(self.client.get('/api/settings/hub/').json()['hub_name'], 'Akala_Express')

    def test_hub_name_cannot_be_empty(self):
        response = self.client.patch('/api/settings/hub/', {'hub_name': '  '}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_reasons_format_must_be_valid(self):
        response = self.client.patch('/api/settings/hub/', {'reasons_format': 'banana'}, format='json')
        self.assertEqual(response.status_code, 400)

    # --- Statuses -----------------------------------------------------------

    def test_list_includes_switched_off_statuses(self):
        self.pending.is_active = False
        self.pending.save()
        names = [s['name'] for s in self.client.get('/api/settings/statuses/').json()]
        self.assertIn('Pending Delivery', names)

    def test_create_status(self):
        response = self.client.post('/api/settings/statuses/', {
            'name': 'Out for Delivery', 'category': 'outstanding', 'sort_order': 3,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(StatusOption.objects.filter(name='Out for Delivery').exists())

    def test_duplicate_status_name_is_refused(self):
        response = self.client.post('/api/settings/statuses/', {
            'name': 'Pending Delivery', 'category': 'outstanding',
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_unused_status_can_change_category(self):
        response = self.client.patch(
            f'/api/settings/statuses/{self.pending.pk}/', {'category': 'returned'}, format='json',
        )
        self.assertEqual(response.status_code, 200)

    def test_used_status_can_be_renamed_but_not_recategorised(self):
        create_shipment('A1', first_seen_date=datetime.date(2026, 10, 26))  # uses "Not Yet Checked"
        url = f'/api/settings/statuses/{self.unchecked.pk}/'

        self.assertEqual(self.client.patch(url, {'name': 'Unchecked'}, format='json').status_code, 200)

        response = self.client.patch(url, {'category': 'delivered'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('category', response.json()['details'])

    def test_used_status_keeps_requires_reason(self):
        unsuccessful = StatusOption.objects.get(name='Delivery Unsuccessful')
        shipment = create_shipment('A1', first_seen_date=datetime.date(2026, 10, 26))
        from shipments.services.status_service import change_status
        change_status(shipment, unsuccessful, failure_reason=FailureReason.objects.first())

        response = self.client.patch(
            f'/api/settings/statuses/{unsuccessful.pk}/', {'requires_reason': False}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_last_unchecked_status_cannot_be_switched_off(self):
        response = self.client.patch(
            f'/api/settings/statuses/{self.unchecked.pk}/', {'is_active': False}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('is_active', response.json()['details'])

    def test_switched_off_status_leaves_the_dropdown(self):
        self.client.patch(f'/api/settings/statuses/{self.pending.pk}/', {'is_active': False}, format='json')
        names = [s['name'] for s in self.client.get('/api/statuses/').json()]
        self.assertNotIn('Pending Delivery', names)

    def test_statuses_cannot_be_deleted(self):
        response = self.client.delete(f'/api/settings/statuses/{self.pending.pk}/')
        self.assertEqual(response.status_code, 405)

    # --- Reasons ------------------------------------------------------------

    def test_create_and_switch_off_reason(self):
        created = self.client.post('/api/settings/reasons/', {'name': 'Bad weather'}, format='json')
        self.assertEqual(created.status_code, 201)

        reason_id = created.json()['id']
        self.client.patch(f'/api/settings/reasons/{reason_id}/', {'is_active': False}, format='json')
        names = [r['name'] for r in self.client.get('/api/reasons/').json()]
        self.assertNotIn('Bad weather', names)

    def test_reasons_cannot_be_deleted(self):
        reason = FailureReason.objects.first()
        self.assertEqual(self.client.delete(f'/api/settings/reasons/{reason.pk}/').status_code, 405)