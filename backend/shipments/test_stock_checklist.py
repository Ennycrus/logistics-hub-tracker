"""
Tests for the stock count tick-off list (GET /api/stock-count/pending/).

Run with:  python manage.py test shipments.test_stock_checklist
"""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import StatusOption

from .services.status_service import change_status, create_shipment

URL = '/api/stock-count/pending/'
MON = datetime.date(2026, 11, 16)
TUE = datetime.date(2026, 11, 17)


class StockChecklistTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        create_shipment('303400000002', first_seen_date=TUE)
        create_shipment('303400000001', first_seen_date=MON)
        create_shipment('1000000001', first_seen_date=MON, shipment_type='base')
        done = create_shipment('303400000003', first_seen_date=MON)
        change_status(done, StatusOption.objects.get(name='Delivered Successfully'),
                      effective_date=TUE, delivered_by='rider')

    def waybills(self, query=''):
        response = self.client.get(f'{URL}{query}')
        self.assertEqual(response.status_code, 200)
        return [r['waybill'] for r in response.json()['results']]

    def test_only_pending_oldest_first(self):
        self.assertEqual(self.waybills(), ['1000000001', '303400000001', '303400000002'])

    def test_one_type(self):
        self.assertEqual(self.waybills('?type=temu'), ['303400000001', '303400000002'])
        self.assertEqual(self.waybills('?type=base'), ['1000000001'])

    def test_rows_have_what_the_page_shows(self):
        row = self.client.get(URL).json()['results'][0]
        self.assertEqual(
            sorted(row), ['arrived', 'days_since_update', 'last_update', 'shipment_id', 'shipment_type',
                          'status', 'waybill'],
        )
        self.assertEqual(self.client.get(URL).json()['count'], 3)

    def test_not_paged(self):
        for n in range(60):
            create_shipment(f'3034100000{n:02d}', first_seen_date=MON)
        self.assertEqual(len(self.waybills()), 63)

    def test_bad_type(self):
        self.assertEqual(self.client.get(f'{URL}?type=boxes').status_code, 400)

    def test_login_required(self):
        self.assertIn(APIClient().get(URL).status_code, (401, 403))