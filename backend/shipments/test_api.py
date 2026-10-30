"""
Tests for the shipments API.

Run with:  python manage.py test shipments

APIClient acts like a browser or React app calling the API.
force_authenticate logs a test user in without a password.
"""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import FailureReason, StatusOption

from .models import Shipment
from .services.status_service import create_shipment

MON = datetime.date(2026, 10, 26)


class ShipmentApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))

        self.delivered = StatusOption.objects.get(name='Delivered Successfully')
        self.unsuccessful = StatusOption.objects.get(name='Delivery Unsuccessful')
        self.unavailable = FailureReason.objects.get(name='Customer unavailable')
        self.other = FailureReason.objects.get(name='Other')

        self.a = create_shipment('TEMU001', first_seen_date=MON)
        self.b = create_shipment('TEMU002', first_seen_date=MON)
        self.c = create_shipment('000123', first_seen_date=MON)

    def status_url(self, shipment):
        return f'/api/shipments/{shipment.pk}/status/'

    # --- Login --------------------------------------------------------------

    def test_login_is_required(self):
        response = APIClient().get('/api/shipments/')
        self.assertEqual(response.status_code, 403)
        self.assertIn('error', response.json())

    # --- Dropdown options ---------------------------------------------------

    def test_status_options_list_active_only(self):
        StatusOption.objects.filter(name='Rerouted to Another Hub').update(is_active=False)
        names = [s['name'] for s in self.client.get('/api/statuses/').json()]
        self.assertIn('Delivered Successfully', names)
        self.assertNotIn('Rerouted to Another Hub', names)

    def test_reason_options(self):
        reasons = self.client.get('/api/reasons/').json()
        self.assertEqual(len(reasons), 6)
        self.assertTrue(next(r for r in reasons if r['name'] == 'Other')['is_other'])

    # --- List, search, filter -----------------------------------------------

    def test_list_is_paginated(self):
        data = self.client.get('/api/shipments/').json()
        self.assertEqual(data['count'], 3)
        self.assertEqual(len(data['results']), 3)

    def test_search_by_waybill(self):
        data = self.client.get('/api/shipments/?search=temu').json()
        self.assertEqual([s['waybill_number'] for s in data['results']], ['TEMU001', 'TEMU002'])

    def test_leading_zeros_come_back_as_text(self):
        data = self.client.get('/api/shipments/?search=000123').json()
        self.assertEqual(data['results'][0]['waybill_number'], '000123')

    def test_filter_by_category(self):
        self.client.post(self.status_url(self.a), {'status': self.delivered.pk}, format='json')
        data = self.client.get('/api/shipments/?category=unchecked').json()
        self.assertEqual(data['count'], 2)

    # --- Detail -------------------------------------------------------------

    def test_detail_includes_history(self):
        data = self.client.get(f'/api/shipments/{self.a.pk}/').json()
        self.assertEqual(len(data['history']), 1)
        self.assertEqual(data['history'][0]['new_status'], 'Not Yet Checked')

    def test_unknown_shipment_is_404(self):
        response = self.client.get('/api/shipments/99999/')
        self.assertEqual(response.status_code, 404)
        self.assertIn('error', response.json())

    # --- Status changes -----------------------------------------------------

    def test_change_status(self):
        response = self.client.post(
            self.status_url(self.a), {'status': self.delivered.pk}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['changed'])
        self.assertEqual(body['shipment']['status_name'], 'Delivered Successfully')
        self.assertEqual(self.a.history.count(), 2)

    def test_missing_reason_gives_clear_400(self):
        response = self.client.post(
            self.status_url(self.a), {'status': self.unsuccessful.pk}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn('requires a failure reason', body['error'])
        self.assertIn('failure_reason', body['details'])

        self.a.refresh_from_db()
        self.assertEqual(self.a.status.name, 'Not Yet Checked')  # nothing saved

    def test_other_reason_needs_note(self):
        response = self.client.post(
            self.status_url(self.a),
            {'status': self.unsuccessful.pk, 'failure_reason': self.other.pk},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('reason_note', response.json()['details'])

    def test_unsuccessful_with_reason(self):
        response = self.client.post(
            self.status_url(self.a),
            {'status': self.unsuccessful.pk, 'failure_reason': self.unavailable.pk,
             'effective_date': str(MON)},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.a.history.last().effective_date, MON)

    def test_unknown_status_id_is_rejected(self):
        response = self.client.post(self.status_url(self.a), {'status': 999}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('status', response.json()['details'])

    def test_future_date_is_rejected(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        response = self.client.post(
            self.status_url(self.a),
            {'status': self.delivered.pk, 'effective_date': str(tomorrow)},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_same_status_twice_reports_no_change(self):
        self.client.post(self.status_url(self.a), {'status': self.delivered.pk}, format='json')
        body = self.client.post(
            self.status_url(self.a), {'status': self.delivered.pk}, format='json',
        ).json()
        self.assertFalse(body['changed'])

    def test_shipments_cannot_be_created_or_deleted_through_api(self):
        self.assertEqual(self.client.post('/api/shipments/', {'waybill_number': 'X'}).status_code, 405)
        self.assertEqual(self.client.delete(f'/api/shipments/{self.a.pk}/').status_code, 405)
        self.assertEqual(Shipment.objects.count(), 3)