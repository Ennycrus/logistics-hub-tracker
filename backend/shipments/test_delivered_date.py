"""
Tests for the delivery-date filter and the delivered_on field.

A delivery is filed under the date it actually happened (effective_date), even
when it is entered a day or two later, so these let you find and see the real
delivery day.

Run with:  python manage.py test shipments.test_delivered_date
"""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import StatusOption
from .services.status_service import change_status, create_shipment

D1 = datetime.date(2026, 11, 2)
D2 = datetime.date(2026, 11, 3)


class DeliveredDateTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        self.delivered = StatusOption.objects.get(name='Delivered Successfully')
        self.pending = StatusOption.objects.get(name='Pending Delivery')

    def deliver(self, waybill, on):
        ship = create_shipment(waybill, first_seen_date=D1)
        change_status(ship, self.delivered, effective_date=on)
        return ship

    def list(self, query=''):
        return self.client.get(f'/api/shipments/{query}').json()['results']

    def test_delivered_on_shows_the_real_delivery_date(self):
        self.deliver('303400000001', D1)
        row = next(r for r in self.list() if r['waybill_number'] == '303400000001')
        self.assertEqual(row['delivered_on'], '2026-11-02')

    def test_pending_shipment_has_no_delivered_on(self):
        ship = create_shipment('303400000009', first_seen_date=D1)
        change_status(ship, self.pending, effective_date=D1)
        row = next(r for r in self.list() if r['waybill_number'] == '303400000009')
        self.assertIsNone(row['delivered_on'])

    def test_filter_by_single_day(self):
        self.deliver('303400000001', D1)
        self.deliver('303400000002', D2)
        rows = self.list('?delivered_from=2026-11-02&delivered_to=2026-11-02')
        self.assertEqual({r['waybill_number'] for r in rows}, {'303400000001'})

    def test_filter_by_range(self):
        self.deliver('303400000001', D1)
        self.deliver('303400000002', D2)
        self.deliver('303400000003', datetime.date(2026, 11, 10))
        rows = self.list('?delivered_from=2026-11-02&delivered_to=2026-11-03')
        self.assertEqual({r['waybill_number'] for r in rows}, {'303400000001', '303400000002'})

    def test_open_sided_range(self):
        self.deliver('303400000001', D1)
        self.deliver('303400000002', datetime.date(2026, 11, 20))
        rows = self.list('?delivered_from=2026-11-10')
        self.assertEqual({r['waybill_number'] for r in rows}, {'303400000002'})

    def test_bad_date_is_refused(self):
        self.assertEqual(self.client.get('/api/shipments/?delivered_from=rubbish').status_code, 400)