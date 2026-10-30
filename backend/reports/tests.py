"""
Tests for reporting days: Inbound, Old Pending and carry-forward.

Run with:  python manage.py test reports
"""

import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from core.models import FailureReason, StatusOption
from shipments.services.status_service import change_status, create_shipment

from .models import DailyShipmentRecord, ReportingDay
from .services.day_service import open_or_refresh_day, statuses_as_of

MON = datetime.date(2026, 10, 26)
TUE = datetime.date(2026, 10, 27)
WED = datetime.date(2026, 10, 28)


class DayServiceTests(TestCase):

    def setUp(self):
        self.pending = StatusOption.objects.get(name='Pending Delivery')
        self.delivered = StatusOption.objects.get(name='Delivered Successfully')
        self.unsuccessful = StatusOption.objects.get(name='Delivery Unsuccessful')
        self.returned = StatusOption.objects.get(name='Returned to Hub')
        self.rerouted = StatusOption.objects.get(name='Rerouted to Another Hub')
        self.unavailable = FailureReason.objects.get(name='Customer unavailable')

    def kinds(self, day):
        """{waybill: kind} for a day, to make assertions easy to read."""
        return {r.shipment.waybill_number: r.kind for r in day.records.select_related('shipment')}

    def test_first_scan_counts_as_inbound(self):
        create_shipment('A', first_seen_date=MON)
        create_shipment('B', first_seen_date=MON)
        day, summary = open_or_refresh_day(MON)

        self.assertEqual(summary['inbound'], 2)
        self.assertEqual(summary['old_pending'], 0)

    def test_undelivered_shipments_carry_forward_as_old_pending(self):
        a = create_shipment('A', first_seen_date=MON)
        b = create_shipment('B', first_seen_date=MON)
        c = create_shipment('C', first_seen_date=MON)
        d = create_shipment('D', first_seen_date=MON)
        change_status(a, self.delivered, effective_date=MON)
        change_status(b, self.unsuccessful, failure_reason=self.unavailable, effective_date=MON)
        change_status(c, self.returned, effective_date=MON)
        change_status(d, self.rerouted, effective_date=MON)
        create_shipment('E', first_seen_date=TUE)

        day, summary = open_or_refresh_day(TUE)

        self.assertEqual(self.kinds(day), {
            'B': DailyShipmentRecord.KIND_OLD_PENDING,  # unsuccessful -> still at hub
            'C': DailyShipmentRecord.KIND_OLD_PENDING,  # returned (rule 4a) -> still at hub
            'E': DailyShipmentRecord.KIND_INBOUND,       # first seen Tuesday
        })  # A delivered and D rerouted are gone
        self.assertEqual(summary['inbound'] + summary['old_pending'], 3)

    def test_unchecked_shipment_carries_forward(self):
        create_shipment('A', first_seen_date=MON)  # never checked
        day, _ = open_or_refresh_day(TUE)
        self.assertEqual(self.kinds(day), {'A': DailyShipmentRecord.KIND_OLD_PENDING})

    def test_rescanned_outstanding_shipment_is_not_inbound_again(self):
        create_shipment('A', first_seen_date=MON)  # still outstanding Tuesday
        day, summary = open_or_refresh_day(TUE)

        self.assertEqual(summary['inbound'], 0)
        self.assertEqual(summary['old_pending'], 1)

    def test_shipment_keeps_carrying_forward_until_delivered(self):
        a = create_shipment('A', first_seen_date=MON)
        change_status(a, self.unsuccessful, failure_reason=self.unavailable, effective_date=MON)
        change_status(a, self.pending, effective_date=TUE)

        tuesday, _ = open_or_refresh_day(TUE)
        self.assertIn('A', self.kinds(tuesday))

        change_status(a, self.delivered, effective_date=TUE)
        wednesday, _ = open_or_refresh_day(WED)
        self.assertNotIn('A', self.kinds(wednesday))

    def test_status_is_read_as_of_the_previous_day(self):
        # Delivered on WEDNESDAY: on Tuesday it was still pending, so Tuesday's
        # Old Pending must include it even though today it shows Delivered.
        a = create_shipment('A', first_seen_date=MON)
        change_status(a, self.delivered, effective_date=WED)

        tuesday, _ = open_or_refresh_day(TUE)
        self.assertIn('A', self.kinds(tuesday))

    def test_skipped_days_still_work(self):
        # Nothing opened on Tuesday: Wednesday still finds Monday's leftovers.
        create_shipment('A', first_seen_date=MON)
        wednesday, _ = open_or_refresh_day(WED)
        self.assertEqual(self.kinds(wednesday), {'A': DailyShipmentRecord.KIND_OLD_PENDING})

    def test_refresh_adds_later_imports_without_duplicates(self):
        create_shipment('A', first_seen_date=MON)
        open_or_refresh_day(MON)
        create_shipment('B', first_seen_date=MON)  # second scan file the same day

        day, summary = open_or_refresh_day(MON)
        _, again = open_or_refresh_day(MON)

        self.assertEqual(summary['added'], 1)
        self.assertEqual(again['added'], 0)
        self.assertEqual(day.records.count(), 2)

    def test_database_blocks_double_counting(self):
        a = create_shipment('A', first_seen_date=MON)
        day, _ = open_or_refresh_day(MON)
        with self.assertRaises(IntegrityError):
            DailyShipmentRecord.objects.create(day=day, shipment=a, kind='old_pending')

    def test_finalized_day_cannot_be_refreshed(self):
        ReportingDay.objects.create(date=MON, state=ReportingDay.STATE_FINALIZED)
        with self.assertRaises(ValidationError):
            open_or_refresh_day(MON)

    def test_statuses_as_of_uses_effective_date(self):
        a = create_shipment('A', first_seen_date=MON)
        change_status(a, self.pending, effective_date=TUE)

        self.assertEqual(statuses_as_of([a.pk], MON)[a.pk].name, 'Not Yet Checked')
        self.assertEqual(statuses_as_of([a.pk], TUE)[a.pk].name, 'Pending Delivery')