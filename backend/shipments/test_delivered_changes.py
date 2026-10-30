"""
Tests for rule C: a delivered shipment can be changed, but only with a note.

Run with:  python manage.py test shipments
"""

import datetime

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import FailureReason, StatusOption

from .services.status_service import change_status, create_shipment

MON = datetime.date(2026, 10, 26)


class DeliveredChangeTests(TestCase):

    def setUp(self):
        self.delivered = StatusOption.objects.get(name='Delivered Successfully')
        self.pending = StatusOption.objects.get(name='Pending Delivery')
        self.unsuccessful = StatusOption.objects.get(name='Delivery Unsuccessful')
        self.unavailable = FailureReason.objects.get(name='Customer unavailable')

        self.shipment = create_shipment('A1', first_seen_date=MON)
        change_status(self.shipment, self.delivered, effective_date=MON)

    def test_changing_delivered_without_note_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            change_status(self.shipment, self.pending)

        self.assertIn('note', caught.exception.message_dict)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.status, self.delivered)  # unchanged
        self.assertEqual(self.shipment.history.count(), 2)     # no new row

    def test_blank_note_does_not_count(self):
        with self.assertRaises(ValidationError):
            change_status(self.shipment, self.pending, note='   ')

    def test_changing_delivered_with_note_is_saved_in_history(self):
        change_status(self.shipment, self.pending, note='Marked delivered by mistake')

        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.status, self.pending)
        self.assertEqual(self.shipment.history.last().note, 'Marked delivered by mistake')

    def test_saving_delivered_again_needs_no_note(self):
        # Nothing actually changes, so there is nothing to explain.
        self.assertFalse(change_status(self.shipment, self.delivered))

    def test_other_statuses_need_no_note(self):
        other = create_shipment('A2', first_seen_date=MON)
        change_status(other, self.unsuccessful, failure_reason=self.unavailable)
        change_status(other, self.pending)  # no note needed
        other.refresh_from_db()
        self.assertEqual(other.status, self.pending)

    def test_api_returns_clear_error(self):
        client = APIClient()
        client.force_authenticate(User.objects.create_user('tester'))
        url = f'/api/shipments/{self.shipment.pk}/status/'

        refused = client.post(url, {'status': self.pending.pk}, format='json')
        self.assertEqual(refused.status_code, 400)
        self.assertIn('already delivered', refused.json()['error'])
        self.assertIn('note', refused.json()['details'])

        allowed = client.post(url, {'status': self.pending.pk, 'note': 'Wrong click'}, format='json')
        self.assertEqual(allowed.status_code, 200)