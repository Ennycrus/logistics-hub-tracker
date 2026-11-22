"""
Tests for the "ready to initiate return" reminder: a shipment with 3+ failed
delivery attempts (Delivery Unsuccessful) that is still at the hub.

Run with:  python manage.py test shipments.test_return_reminder
"""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import FailureReason, StatusOption

from .models import Shipment
from .services.status_service import change_status, create_shipment

MON = datetime.date(2026, 11, 16)


def fail(shipment, day):
    unsuccessful = StatusOption.objects.get(name='Delivery Unsuccessful')
    reason = FailureReason.objects.first()
    change_status(shipment, unsuccessful, effective_date=day, failure_reason=reason)


@override_settings(RETURN_AFTER_ATTEMPTS=3)
class ReturnReminderTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        self.ship = create_shipment('303400000001', first_seen_date=MON)

    def row(self):
        results = self.client.get('/api/shipments/').json()['results']
        return next(r for r in results if r['waybill_number'] == '303400000001')

    def test_counts_only_failed_attempts(self):
        fail(self.ship, datetime.date(2026, 11, 17))
        fail(self.ship, datetime.date(2026, 11, 18))
        row = self.row()
        self.assertEqual(row['attempt_count'], 2)
        self.assertFalse(row['ready_for_return'])

    def test_three_attempts_flags_ready_for_return(self):
        for d in (17, 18, 19):
            fail(self.ship, datetime.date(2026, 11, d))
        row = self.row()
        self.assertEqual(row['attempt_count'], 3)
        self.assertTrue(row['ready_for_return'])

    def test_once_returned_it_no_longer_reminds(self):
        for d in (17, 18, 19):
            fail(self.ship, datetime.date(2026, 11, d))
        initiated = StatusOption.objects.create(
            name='Initiated Return', category=StatusOption.CATEGORY_LEFT_HUB,
        )
        change_status(self.ship, initiated, effective_date=datetime.date(2026, 11, 19), note='3 attempts')
        row = self.row()
        self.assertEqual(row['attempt_count'], 3)   # history still shows the 3 attempts
        self.assertFalse(row['ready_for_return'])   # but it has left the hub, so no reminder

    def test_filter_lists_only_ready_shipments(self):
        other = create_shipment('303400000002', first_seen_date=MON)
        for d in (17, 18, 19):
            fail(self.ship, datetime.date(2026, 11, d))
        fail(other, datetime.date(2026, 11, 17))  # only one attempt
        results = self.client.get('/api/shipments/?ready_for_return=1').json()['results']
        self.assertEqual([r['waybill_number'] for r in results], ['303400000001'])

    def test_detail_and_single_change_response_carry_the_count(self):
        for d in (17, 18, 19):
            fail(self.ship, datetime.date(2026, 11, d))
        detail = self.client.get(f'/api/shipments/{self.ship.pk}/').json()
        self.assertEqual((detail['attempt_count'], detail['ready_for_return']), (3, True))
        # The single status-change response is not annotated; it must still compute the count.
        done = StatusOption.objects.get(name='Delivered Successfully')
        resp = self.client.post(f'/api/shipments/{self.ship.pk}/status/', {
            'status': done.pk, 'effective_date': '2026-11-20', 'delivered_by': 'rider',
            'note': 'finally delivered',
        }, format='json').json()
        # The serialized shipment here is NOT annotated, so the count is computed from history.
        self.assertEqual(resp['shipment']['attempt_count'], 3)
        self.assertFalse(resp['shipment']['ready_for_return'])  # delivered now, so no reminder
        

    def test_last_update_is_the_latest_history_date(self):
        fail(self.ship, datetime.date(2026, 11, 17))
        fail(self.ship, datetime.date(2026, 11, 18))
        self.assertEqual(self.row()['last_update'], '2026-11-18')

    def test_a_repeat_unsuccessful_on_a_later_day_adds_an_attempt(self):
        # Same status and reason, just a later date: must be recorded as a new attempt.
        unsuccessful = StatusOption.objects.get(name='Delivery Unsuccessful')
        reason = FailureReason.objects.first()
        body = lambda day: {  # noqa: E731
            'status': unsuccessful.pk, 'failure_reason': reason.pk, 'effective_date': day,
        }
        for day in ('2026-11-17', '2026-11-18', '2026-11-19'):
            self.client.post(f'/api/shipments/{self.ship.pk}/status/', body(day), format='json')
        row = self.row()
        self.assertEqual(row['attempt_count'], 3)
        self.assertTrue(row['ready_for_return'])
        # Same date again changes nothing (no duplicate attempt).
        resp = self.client.post(f'/api/shipments/{self.ship.pk}/status/', body('2026-11-19'),
                                format='json').json()
        self.assertFalse(resp['changed'])
        self.assertEqual(self.row()['attempt_count'], 3)

    def test_hub_settings_exposes_the_threshold(self):
        data = self.client.get('/api/settings/hub/').json()
        self.assertIn('return_after_attempts', data)