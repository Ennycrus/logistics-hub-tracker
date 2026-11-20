"""
Tests for the stock count (compare the shelves with the app).

Run with:  python manage.py test shipments.test_stock_count
"""

import datetime

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import StatusOption

from .models import ImportBatch, Shipment, StatusHistory
from .services.status_service import change_status, create_shipment
from .services.stock_count import stock_count
from .test_excel_reader import make_xlsx

MON = datetime.date(2026, 11, 16)
T1, T2, T3, T4, T5 = (f'30340000000{n}' for n in range(1, 6))
B1, B2 = '1000000001', '1000000002'


class StockCountTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        delivered = StatusOption.objects.get(name='Delivered Successfully')
        create_shipment(T1, first_seen_date=MON)          # pending, on the shelf
        create_shipment(T2, first_seen_date=MON)          # pending, NOT on the shelf
        done = create_shipment(T3, first_seen_date=MON)   # delivered, but on the shelf
        change_status(done, delivered, effective_date=MON, delivered_by='rider')
        create_shipment(B1, first_seen_date=MON, shipment_type='base')  # pending Base, NOT on the shelf

    def scan(self, *waybills):
        return make_xlsx([['Waybill'], *[[w] for w in waybills]])

    def waybills(self, rows):
        return [r['waybill'] for r in rows]

    def test_every_group(self):
        # T4 was never imported; T1 is scanned twice (a duplicate is one parcel).
        result = stock_count(self.scan(T1, T3, T4, T1, 'BAD ONE'))
        self.assertEqual(result['matched'], 1)
        self.assertEqual(self.waybills(result['missing']), [B1, T2])
        self.assertEqual(self.waybills(result['closed']), [T3])
        self.assertEqual(result['closed'][0]['status'], 'Delivered Successfully')
        self.assertEqual(result['not_in_app'], [{'waybill': T4, 'shipment_type': 'temu'}])
        self.assertEqual((result['scanned'], result['pending_in_app']), (3, 3))

    def test_everything_on_the_shelf(self):
        result = stock_count(self.scan(T1, T2, B1))
        self.assertEqual((result['matched'], result['missing'], result['closed'], result['not_in_app']),
                         (3, [], [], []))

    def test_one_type_only(self):
        result = stock_count(self.scan(T1, B2), shipment_type='temu')
        self.assertEqual(self.waybills(result['missing']), [T2])  # the Base parcel B1 is not expected
        self.assertEqual(result['not_in_app'], [])                 # the Base scan B2 is left out
        self.assertEqual(result['other_type'], 1)

    def test_missing_rows_show_status_and_dates(self):
        row = stock_count(self.scan(T1))['missing'][-1]
        self.assertEqual(row['waybill'], T2)
        self.assertEqual((row['status'], row['arrived'], row['last_update']), ('Not Yet Checked', MON, MON))

    def test_nothing_is_saved(self):
        before = (Shipment.objects.count(), StatusHistory.objects.count(), ImportBatch.objects.count())
        stock_count(self.scan(T1, T4))
        self.assertEqual(
            (Shipment.objects.count(), StatusHistory.objects.count(), ImportBatch.objects.count()), before,
        )

    def test_column_must_be_chosen_when_unclear(self):
        result = stock_count(make_xlsx([['A', 'B'], [T1, 'x']]))
        self.assertIsNone(result['selected_column'])
        self.assertNotIn('missing', result)

    def test_through_the_api(self):
        upload = SimpleUploadedFile('shelves.txt', f'{T1}\n{T4}\n'.encode())
        response = self.client.post('/api/stock-count/', {'file': upload, 'shipment_type': 'temu'},
                                    format='multipart')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual((data['matched'], data['file_name']), (1, 'shelves.txt'))
        self.assertEqual(self.waybills(data['missing']), [T2])

    def test_bad_type_is_refused(self):
        upload = SimpleUploadedFile('shelves.txt', f'{T1}\n'.encode())
        response = self.client.post('/api/stock-count/', {'file': upload, 'shipment_type': 'boxes'},
                                    format='multipart')
        self.assertEqual(response.status_code, 400)