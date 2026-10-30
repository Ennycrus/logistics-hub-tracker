"""
Tests for the Shipment model and the status service.

Run with:  python manage.py test shipments

Django creates a separate, temporary test database for every run (it never
touches db.sqlite3). Our seed migration runs there too, so the default
statuses and reasons already exist in every test.
"""

import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import FailureReason, StatusOption

from .models import Shipment, StatusHistory
from .services.status_service import change_status, create_shipment

MONDAY = datetime.date(2026, 10, 26)
TUESDAY = datetime.date(2026, 10, 27)


class StatusServiceTests(TestCase):

    def setUp(self):
        # setUp runs before EVERY test, giving each one fresh objects.
        self.unchecked = StatusOption.objects.get(name='Not Yet Checked')
        self.pending = StatusOption.objects.get(name='Pending Delivery')
        self.delivered = StatusOption.objects.get(name='Delivered Successfully')
        self.unsuccessful = StatusOption.objects.get(name='Delivery Unsuccessful')
        self.returned = StatusOption.objects.get(name='Returned to Hub')
        self.unavailable = FailureReason.objects.get(name='Customer unavailable')
        self.other = FailureReason.objects.get(name='Other')

        self.shipment = create_shipment('TEMU001', first_seen_date=MONDAY)

    # --- Creating shipments -------------------------------------------------

    def test_new_shipment_starts_unchecked_with_one_history_row(self):
        self.assertEqual(self.shipment.status, self.unchecked)
        self.assertEqual(self.shipment.history.count(), 1)
        self.assertIsNone(self.shipment.history.first().old_status)

    def test_leading_zeros_are_kept(self):
        shipment = create_shipment('000123', first_seen_date=MONDAY)
        shipment.refresh_from_db()  # re-read from the database
        self.assertEqual(shipment.waybill_number, '000123')

    def test_spaces_around_waybill_are_removed(self):
        shipment = create_shipment('  TEMU002  ', first_seen_date=MONDAY)
        self.assertEqual(shipment.waybill_number, 'TEMU002')

    def test_duplicate_waybill_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_shipment('TEMU001', first_seen_date=TUESDAY)
        self.assertEqual(Shipment.objects.filter(waybill_number='TEMU001').count(), 1)

    def test_empty_waybill_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_shipment('   ', first_seen_date=MONDAY)

    # --- Changing status ----------------------------------------------------

    def test_status_change_updates_shipment_and_writes_history(self):
        changed = change_status(self.shipment, self.delivered, effective_date=MONDAY)
        self.shipment.refresh_from_db()

        self.assertTrue(changed)
        self.assertEqual(self.shipment.status, self.delivered)
        self.assertEqual(self.shipment.history.count(), 2)
        last = self.shipment.history.last()
        self.assertEqual(last.old_status, self.unchecked)
        self.assertEqual(last.new_status, self.delivered)

    def test_unsuccessful_without_reason_is_rejected_and_nothing_saved(self):
        with self.assertRaises(ValidationError):
            change_status(self.shipment, self.unsuccessful, effective_date=MONDAY)
        self.shipment.refresh_from_db()

        self.assertEqual(self.shipment.status, self.unchecked)  # unchanged
        self.assertEqual(self.shipment.history.count(), 1)      # no new row

    def test_other_reason_requires_a_note(self):
        with self.assertRaises(ValidationError):
            change_status(self.shipment, self.unsuccessful, failure_reason=self.other)

    def test_other_reason_with_note_is_saved(self):
        change_status(
            self.shipment, self.unsuccessful,
            failure_reason=self.other, reason_note='Gate locked', effective_date=MONDAY,
        )
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.reason_note, 'Gate locked')

    def test_reason_is_cleared_when_status_no_longer_needs_it(self):
        change_status(self.shipment, self.unsuccessful, failure_reason=self.unavailable)
        change_status(self.shipment, self.delivered)
        self.shipment.refresh_from_db()

        self.assertEqual(self.shipment.status, self.delivered)
        self.assertIsNone(self.shipment.failure_reason)
        # ...but the old reason is still visible in history.
        self.assertTrue(
            self.shipment.history.filter(failure_reason=self.unavailable).exists()
        )

    def test_saving_same_status_again_writes_no_history(self):
        change_status(self.shipment, self.pending)
        changed = change_status(self.shipment, self.pending)

        self.assertFalse(changed)
        self.assertEqual(self.shipment.history.count(), 2)  # created + 1 change

    def test_inactive_status_cannot_be_used(self):
        self.pending.is_active = False
        self.pending.save()
        with self.assertRaises(ValidationError):
            change_status(self.shipment, self.pending)

    # --- The full story from the spec --------------------------------------

    def test_full_history_is_preserved_across_days(self):
        change_status(self.shipment, self.unsuccessful,
                      failure_reason=self.unavailable, effective_date=MONDAY)
        change_status(self.shipment, self.returned, effective_date=MONDAY)
        change_status(self.shipment, self.pending, effective_date=TUESDAY)
        change_status(self.shipment, self.delivered, effective_date=TUESDAY)

        # Still exactly ONE shipment...
        self.assertEqual(Shipment.objects.filter(waybill_number='TEMU001').count(), 1)

        # ...with every step recorded, in order.
        steps = list(
            StatusHistory.objects.filter(shipment=self.shipment)
            .values_list('new_status__name', 'effective_date')
        )
        self.assertEqual(steps, [
            ('Not Yet Checked', MONDAY),
            ('Delivery Unsuccessful', MONDAY),
            ('Returned to Hub', MONDAY),
            ('Pending Delivery', TUESDAY),
            ('Delivered Successfully', TUESDAY),
        ])