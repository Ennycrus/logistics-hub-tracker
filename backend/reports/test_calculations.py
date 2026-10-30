"""
Tests for the daily figures.

Run with:  python manage.py test reports
"""

import datetime

from django.test import TestCase

from core.models import FailureReason, HubConfig, StatusOption
from shipments.models import Shipment
from shipments.services.status_service import change_status, create_shipment

from .services.calculations import calculate_day
from .services.day_service import open_or_refresh_day

MON = datetime.date(2026, 10, 26)
TUE = datetime.date(2026, 10, 27)


class CalculationTests(TestCase):

    def setUp(self):
        self.pending = StatusOption.objects.get(name='Pending Delivery')
        self.delivered = StatusOption.objects.get(name='Delivered Successfully')
        self.unsuccessful = StatusOption.objects.get(name='Delivery Unsuccessful')
        self.returned = StatusOption.objects.get(name='Returned to Hub')
        self.rerouted = StatusOption.objects.get(name='Rerouted to Another Hub')
        self.unavailable = FailureReason.objects.get(name='Customer unavailable')
        self.reschedule = FailureReason.objects.get(name='Customer requested rescheduling')
        self.other = FailureReason.objects.get(name='Other')

    def make(self, waybill, status=None, reason=None, note='', date=MON):
        shipment = create_shipment(waybill, first_seen_date=date)
        if status:
            change_status(shipment, status, failure_reason=reason, reason_note=note, effective_date=date)
        return shipment

    def summary(self, date):
        day, _ = open_or_refresh_day(date)
        return calculate_day(day)

    def test_total_available_is_inbound_plus_old_pending(self):
        self.make('OLD1', self.unsuccessful, self.unavailable, date=MON)
        self.make('OLD2', self.pending, date=MON)
        self.make('NEW1', date=TUE)

        f = self.summary(TUE)['figures']
        self.assertEqual(f['inbound'], 1)
        self.assertEqual(f['old_pending'], 2)
        self.assertEqual(f['total_available'], 3)

    def test_full_day_figures(self):
        self.make('D1', self.delivered)
        self.make('D2', self.delivered)
        self.make('U1', self.unsuccessful, self.unavailable)
        self.make('P1', self.pending)
        self.make('R1', self.returned)
        self.make('X1', self.rerouted)

        result = self.summary(MON)
        f = result['figures']
        self.assertEqual(f['total_available'], 6)
        self.assertEqual(f['delivered'], 2)
        self.assertEqual(f['current_day'], 3)   # U1 + P1 + R1
        self.assertEqual(f['return'], 1)        # R1, also inside Current Day
        self.assertEqual(f['rerouted'], 1)
        self.assertEqual(f['unsuccessful'], 1)
        self.assertTrue(result['reconciliation']['balanced'])
        self.assertEqual(result['warnings'], [])

    def test_current_day_is_not_just_unsuccessful(self):
        self.make('U1', self.unsuccessful, self.unavailable)
        self.make('P1', self.pending)
        f = self.summary(MON)['figures']
        self.assertEqual(f['unsuccessful'], 1)
        self.assertEqual(f['current_day'], 2)

    def test_unchecked_are_counted_in_current_day_with_a_warning(self):
        self.make('A')  # never checked
        result = self.summary(MON)

        self.assertEqual(result['figures']['current_day'], 1)
        self.assertEqual([w['code'] for w in result['warnings']], ['unchecked'])

    def test_figures_use_status_at_end_of_that_day(self):
        a = self.make('A', self.pending, date=MON)
        change_status(a, self.delivered, effective_date=TUE)  # delivered the NEXT day

        monday = self.summary(MON)['figures']
        self.assertEqual(monday['delivered'], 0)
        self.assertEqual(monday['current_day'], 1)

    def test_reasons_are_grouped_and_sorted(self):
        self.make('U1', self.unsuccessful, self.unavailable)
        self.make('U2', self.unsuccessful, self.unavailable)
        self.make('U3', self.unsuccessful, self.reschedule)
        self.make('U4', self.unsuccessful, self.other, note='Gate locked')
        self.make('D1', self.delivered)

        result = self.summary(MON)
        self.assertEqual(
            result['reasons_text'],
            'Customer unavailable - 2; Customer requested rescheduling - 1; Other (Gate locked) - 1',
        )

    def test_text_format_leaves_reasons_for_manual_entry(self):
        config = HubConfig.get()
        config.reasons_format = HubConfig.REASONS_FORMAT_TEXT
        config.save()
        self.make('U1', self.unsuccessful, self.unavailable)

        result = self.summary(MON)
        self.assertEqual(result['reasons_text'], '')
        self.assertEqual(len(result['reasons']), 1)  # the counts are still available

    def test_shipment_without_history_is_flagged_and_does_not_balance(self):
        self.make('A', self.delivered)
        # Simulate old test data made before the status service existed.
        Shipment.objects.create(
            waybill_number='NOHIST', status=self.pending, first_seen_date=MON,
        )

        result = self.summary(MON)
        codes = [w['code'] for w in result['warnings']]
        self.assertIn('no_history', codes)
        self.assertIn('does_not_reconcile', codes)
        self.assertFalse(result['reconciliation']['balanced'])