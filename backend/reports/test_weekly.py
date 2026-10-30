"""
Tests for the weekly delivery summary (Monday to Saturday, finalized reports only).

Run with:  python manage.py test reports
"""

import datetime
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from openpyxl import load_workbook
from rest_framework.test import APIClient

from core.models import StatusOption
from shipments.models import TYPE_BASE, TYPE_TEMU
from shipments.services.status_service import change_status, create_shipment

from .services.report_service import finalize, get_or_create_draft, save_draft
from .services.weekly import week_start, weekly_summary

MON = datetime.date(2026, 10, 19)
TUE = datetime.date(2026, 10, 20)
WED = datetime.date(2026, 10, 21)
SAT = datetime.date(2026, 10, 24)
SUN = datetime.date(2026, 10, 25)


def finalize_day(date, shipment_type=TYPE_TEMU):
    draft = save_draft(get_or_create_draft(date, shipment_type), vans=1, bikes=1, third_party=0)
    return finalize(draft, accept_warnings=True)


class WeekStartTests(TestCase):

    def test_monday_to_saturday_belong_to_that_monday(self):
        self.assertEqual(week_start(MON), MON)
        self.assertEqual(week_start(SAT), MON)

    def test_sunday_belongs_to_the_week_before(self):
        self.assertEqual(week_start(SUN), MON)


class WeeklySummaryTests(TestCase):

    def setUp(self):
        delivered = StatusOption.objects.get(name='Delivered Successfully')
        # Monday: 3 TEMU in, 1 delivered.  Tuesday: 1 more in, 1 more delivered.
        a = create_shipment('3034000001', first_seen_date=MON)
        b = create_shipment('3034000002', first_seen_date=MON)
        create_shipment('3034000003', first_seen_date=MON)
        change_status(a, delivered, effective_date=MON)
        # A Base shipment delivered on Monday must not count for TEMU.
        change_status(create_shipment('1000000001', first_seen_date=MON, shipment_type=TYPE_BASE),
                      delivered, effective_date=MON)
        finalize_day(MON)

        create_shipment('3034000004', first_seen_date=TUE)
        change_status(b, delivered, effective_date=TUE)
        finalize_day(TUE)

    def test_each_day_has_its_own_rate(self):
        days = weekly_summary(WED)['days']
        self.assertEqual([d['weekday'] for d in days],
                         ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'])
        self.assertEqual((days[0]['total_available'], days[0]['delivered'], days[0]['rate']), (3, 1, 33.3))
        self.assertEqual((days[1]['total_available'], days[1]['delivered'], days[1]['rate']), (3, 1, 33.3))

    def test_week_counts_each_shipment_once(self):
        totals = weekly_summary(WED)['totals']
        # Available = Monday's Old Pending (0) + inbound Mon-Sat (3 + 1) = 4,
        # NOT the sum of daily Total Available (3 + 3 = 6).
        self.assertEqual(totals['delivered'], 2)
        self.assertEqual(totals['available'], 4)
        self.assertEqual(totals['rate'], 50.0)

    def test_unfinalized_days_are_listed_as_missing(self):
        summary = weekly_summary(WED)
        self.assertFalse(summary['complete'])
        self.assertEqual(len(summary['missing']), 4)
        self.assertFalse(summary['days'][2]['finalized'])

    def test_base_is_counted_separately(self):
        finalize_day(MON, TYPE_BASE)
        base = weekly_summary(WED, TYPE_BASE)['totals']
        self.assertEqual((base['delivered'], base['available'], base['rate']), (1, 1, 100.0))

    def test_no_weekly_rate_without_monday(self):
        summary = weekly_summary(datetime.date(2026, 10, 28))  # a week with nothing finalized
        self.assertIsNone(summary['totals']['rate'])
        self.assertEqual(summary['totals']['delivered'], 0)


class WeeklyApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        create_shipment('3034000001', first_seen_date=MON)
        finalize_day(MON)

    def test_summary_endpoint(self):
        body = self.client.get(f'/api/reports/weekly/?date={WED}&type=temu').json()
        self.assertEqual(body['week_start'], str(MON))
        self.assertEqual(body['week_end'], str(SAT))
        self.assertEqual(body['totals']['available'], 1)

    def test_download_is_an_excel_file(self):
        response = self.client.get(f'/api/reports/weekly/download/?date={WED}&type=temu')
        self.assertEqual(response.status_code, 200)
        self.assertIn('_TEMU_week_2026-10-19.xlsx', response['Content-Disposition'])
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertEqual(sheet['A1'].value, 'Weekly Delivery - TEMU')
        self.assertIn('Incomplete', sheet['A3'].value)

    def test_bad_type_is_refused(self):
        self.assertEqual(self.client.get('/api/reports/weekly/?type=parcel').status_code, 400)