"""
Tests for bulk status updates (all or nothing).

Run with:  python manage.py test shipments
"""

import datetime

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import FailureReason, StatusOption

from .models import StatusHistory
from .services.status_service import MAX_BULK, bulk_change_status, change_status, create_shipment

MON = datetime.date(2026, 10, 26)
URL = '/api/shipments/bulk-status/'


class BulkStatusTests(TestCase):

    def setUp(self):
        self.delivered = StatusOption.objects.get(name='Delivered Successfully')
        self.pending = StatusOption.objects.get(name='Pending Delivery')
        self.unsuccessful = StatusOption.objects.get(name='Delivery Unsuccessful')
        self.unavailable = FailureReason.objects.get(name='Customer unavailable')
        self.a = create_shipment('A1', first_seen_date=MON)
        self.b = create_shipment('B1', first_seen_date=MON)
        self.c = create_shipment('C1', first_seen_date=MON)

        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))

    def refresh(self):
        for s in (self.a, self.b, self.c):
            s.refresh_from_db()

    # --- Service ------------------------------------------------------------

    def test_all_selected_shipments_change_with_history(self):
        result = bulk_change_status([self.a.pk, self.b.pk], self.delivered, effective_date=MON)
        self.refresh()

        self.assertEqual(result, {'changed': 2, 'unchanged': 0, 'failures': []})
        self.assertEqual(self.a.status, self.delivered)
        self.assertEqual(self.b.status, self.delivered)
        self.assertEqual(self.c.status.name, 'Not Yet Checked')  # not selected, untouched
        self.assertEqual(StatusHistory.objects.filter(new_status=self.delivered).count(), 2)

    def test_reason_is_applied_to_every_shipment(self):
        bulk_change_status([self.a.pk, self.b.pk], self.unsuccessful, failure_reason=self.unavailable)
        self.refresh()
        self.assertEqual(self.a.failure_reason, self.unavailable)
        self.assertEqual(self.b.failure_reason, self.unavailable)

    def test_one_failure_means_nothing_is_saved(self):
        change_status(self.b, self.delivered)  # B is delivered: changing it needs a note
        history_before = StatusHistory.objects.count()

        result = bulk_change_status([self.a.pk, self.b.pk, self.c.pk], self.pending)
        self.refresh()

        self.assertEqual([f['waybill_number'] for f in result['failures']], ['B1'])
        self.assertEqual(self.a.status.name, 'Not Yet Checked')  # rolled back
        self.assertEqual(self.c.status.name, 'Not Yet Checked')  # rolled back
        self.assertEqual(StatusHistory.objects.count(), history_before)

    def test_note_lets_delivered_shipments_change_in_bulk(self):
        change_status(self.b, self.delivered)
        result = bulk_change_status([self.a.pk, self.b.pk], self.pending, note='Wrong batch marked')
        self.assertEqual(result['changed'], 2)

    def test_unchanged_shipments_are_counted(self):
        change_status(self.a, self.pending)
        result = bulk_change_status([self.a.pk, self.b.pk], self.pending)
        self.assertEqual(result, {'changed': 1, 'unchanged': 1, 'failures': []})

    def test_repeated_ids_count_once(self):
        result = bulk_change_status([self.a.pk, self.a.pk], self.pending)
        self.assertEqual(result['changed'], 1)

    def test_missing_shipment_is_refused(self):
        with self.assertRaises(ValidationError):
            bulk_change_status([self.a.pk, 99999], self.pending)

    def test_too_many_is_refused(self):
        with self.assertRaises(ValidationError):
            bulk_change_status(list(range(1, MAX_BULK + 2)), self.pending)

    # --- API ----------------------------------------------------------------

    def test_api_bulk_update(self):
        response = self.client.post(URL, {
            'shipment_ids': [self.a.pk, self.b.pk], 'status': self.delivered.pk,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['changed'], 2)

    def test_api_lists_failures_and_saves_nothing(self):
        response = self.client.post(URL, {
            'shipment_ids': [self.a.pk, self.b.pk], 'status': self.unsuccessful.pk,
        }, format='json')  # no reason given
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn('nothing was saved', body['error'])
        self.assertEqual(len(body['details']['failures']), 2)
        self.refresh()
        self.assertEqual(self.a.status.name, 'Not Yet Checked')

    def test_api_needs_at_least_one_shipment(self):
        response = self.client.post(URL, {'shipment_ids': [], 'status': self.pending.pk}, format='json')
        self.assertEqual(response.status_code, 400)
        