"""
Tests for the list of shipments in a day's report (the Pending page).

Run with:  python manage.py test reports
"""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import FailureReason, StatusOption
from shipments.services.status_service import change_status, create_shipment

from .services.report_service import finalize, get_or_create_draft, save_draft

MON = datetime.date(2026, 10, 26)
TUE = datetime.date(2026, 10, 27)
WED = datetime.date(2026, 10, 28)


class DayShipmentsApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        self.delivered = StatusOption.objects.get(name='Delivered Successfully')
        self.unsuccessful = StatusOption.objects.get(name='Delivery Unsuccessful')
        unavailable = FailureReason.objects.get(name='Customer unavailable')

        # Monday: A delivered, B unsuccessful. Tuesday: C is new.
        change_status(create_shipment('A', first_seen_date=MON), self.delivered, effective_date=MON)
        self.b = create_shipment('B', first_seen_date=MON)
        change_status(self.b, self.unsuccessful, failure_reason=unavailable, effective_date=MON)
        create_shipment('C', first_seen_date=TUE)

    def get(self, date, **params):
        return self.client.get(f'/api/reports/{date}/shipments/', params)

    def waybills(self, response):
        return [r['shipment']['waybill_number'] for r in response.json()['results']]

    def test_lists_old_pending_and_inbound(self):
        body = self.get(TUE).json()
        kinds = {r['shipment']['waybill_number']: r['kind'] for r in body['results']}
        self.assertEqual(kinds, {'B': 'old_pending', 'C': 'inbound'})  # A was delivered

    def test_filter_by_kind(self):
        self.assertEqual(self.waybills(self.get(TUE, kind='old_pending')), ['B'])
        self.assertEqual(self.waybills(self.get(TUE, kind='inbound')), ['C'])

    def test_filter_by_category_and_search(self):
        self.assertEqual(self.waybills(self.get(TUE, category='unchecked')), ['C'])
        self.assertEqual(self.waybills(self.get(TUE, search='b')), ['B'])

    def test_days_at_hub(self):
        create_shipment('D', first_seen_date=MON)  # still unchecked on Wednesday
        rows = {r['shipment']['waybill_number']: r['days_at_hub'] for r in self.get(WED).json()['results']}
        self.assertEqual(rows['B'], 2)
        self.assertEqual(rows['D'], 2)
        self.assertEqual(rows['C'], 1)

    def test_longest_waiting_first(self):
        self.assertEqual(self.waybills(self.get(WED)), ['B', 'C'])

    def test_shows_current_status(self):
        change_status(self.b, self.delivered, effective_date=TUE)
        row = self.get(TUE, kind='old_pending').json()['results'][0]
        self.assertEqual(row['shipment']['status_name'], 'Delivered Successfully')

    def test_open_day_list_is_refreshed(self):
        self.get(TUE)
        create_shipment('LATE', first_seen_date=TUE)  # imported later the same day
        self.assertIn('LATE', self.waybills(self.get(TUE)))

    def test_finalized_day_list_is_frozen(self):
        finalize(save_draft(get_or_create_draft(TUE), vans=1, bikes=1, third_party=0),
                 accept_warnings=True)
        create_shipment('LATE', first_seen_date=TUE)
        self.assertNotIn('LATE', self.waybills(self.get(TUE)))

    def test_bad_and_future_dates(self):
        self.assertEqual(self.get('27-10-2026').status_code, 400)
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        self.assertEqual(self.get(tomorrow).status_code, 400)