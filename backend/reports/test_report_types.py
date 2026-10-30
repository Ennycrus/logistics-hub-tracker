"""
Tests that the Base and TEMU reports are counted completely separately.

Run with:  python manage.py test reports
"""

import datetime

from django.test import TestCase

from core.models import FailureReason, StatusOption
from shipments.models import TYPE_BASE, TYPE_TEMU
from shipments.services.status_service import change_status, create_shipment

from .models import ReportingDay
from .services.calculations import calculate_day
from .services.day_service import open_or_refresh_day
from .services.report_service import (
    current_report, finalize, get_or_create_draft, save_draft, start_correction,
)

MON = datetime.date(2026, 10, 26)
TUE = datetime.date(2026, 10, 27)


class ReportTypeTests(TestCase):

    def setUp(self):
        self.delivered = StatusOption.objects.get(name='Delivered Successfully')
        self.unsuccessful = StatusOption.objects.get(name='Delivery Unsuccessful')
        unavailable = FailureReason.objects.get(name='Customer unavailable')

        # Monday: 3 TEMU (1 delivered), 2 Base (1 unsuccessful).
        change_status(create_shipment('3034001', first_seen_date=MON), self.delivered, effective_date=MON)
        create_shipment('3034002', first_seen_date=MON)
        create_shipment('3034003', first_seen_date=MON)
        create_shipment('1001', first_seen_date=MON, shipment_type=TYPE_BASE)
        change_status(
            create_shipment('1002', first_seen_date=MON, shipment_type=TYPE_BASE),
            self.unsuccessful, failure_reason=unavailable, effective_date=MON,
        )

    def figures(self, date, shipment_type):
        day, _ = open_or_refresh_day(date, shipment_type)
        return calculate_day(day)

    def test_each_report_counts_only_its_own_shipments(self):
        temu = self.figures(MON, TYPE_TEMU)['figures']
        base = self.figures(MON, TYPE_BASE)['figures']

        self.assertEqual((temu['inbound'], temu['delivered'], temu['current_day']), (3, 1, 2))
        self.assertEqual((base['inbound'], base['delivered'], base['current_day']), (2, 0, 2))

    def test_reasons_are_separate(self):
        self.assertEqual(self.figures(MON, TYPE_TEMU)['reasons_text'], '')
        self.assertEqual(self.figures(MON, TYPE_BASE)['reasons_text'], 'Customer unavailable - 1')

    def test_carry_forward_is_separate(self):
        create_shipment('3034004', first_seen_date=TUE)
        temu = self.figures(TUE, TYPE_TEMU)['figures']
        base = self.figures(TUE, TYPE_BASE)['figures']

        self.assertEqual((temu['inbound'], temu['old_pending']), (1, 2))
        self.assertEqual((base['inbound'], base['old_pending']), (0, 2))

    def test_two_separate_days_for_the_same_date(self):
        open_or_refresh_day(MON, TYPE_TEMU)
        open_or_refresh_day(MON, TYPE_BASE)
        self.assertEqual(ReportingDay.objects.filter(date=MON).count(), 2)

    def test_finalizing_one_type_leaves_the_other_open(self):
        draft = save_draft(get_or_create_draft(MON, TYPE_TEMU), vans=1, bikes=2, third_party=0)
        finalize(draft, accept_warnings=True)

        base_draft = get_or_create_draft(MON, TYPE_BASE)  # still allowed
        self.assertFalse(base_draft.is_finalized)
        self.assertIsNone(current_report(MON, TYPE_BASE))
        self.assertIsNotNone(current_report(MON, TYPE_TEMU))

    def test_transport_figures_are_separate(self):
        save_draft(get_or_create_draft(MON, TYPE_TEMU), vans=3, bikes=1, third_party=0)
        save_draft(get_or_create_draft(MON, TYPE_BASE), vans=1, bikes=4, third_party=2)

        self.assertEqual(get_or_create_draft(MON, TYPE_TEMU).vans, 3)
        self.assertEqual(get_or_create_draft(MON, TYPE_BASE).vans, 1)

    def test_corrections_are_per_type(self):
        for t in (TYPE_TEMU, TYPE_BASE):
            finalize(save_draft(get_or_create_draft(MON, t), vans=1, bikes=1, third_party=0),
                     accept_warnings=True)

        correction = start_correction(MON, 'Fix Base vans', shipment_type=TYPE_BASE)
        self.assertEqual(correction.day.shipment_type, TYPE_BASE)
        self.assertEqual(current_report(MON, TYPE_TEMU).version, 1)