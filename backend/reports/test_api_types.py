"""
Tests for ?type=base / ?type=temu across the API.

Run with:  python manage.py test reports
"""

import datetime

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import StatusOption
from shipments.models import TYPE_BASE, Shipment
from shipments.services.status_service import change_status, create_shipment
from shipments.test_excel_reader import make_xlsx

MON = datetime.date(2026, 10, 26)
URL = f'/api/reports/{MON}/'
TRANSPORT = {'vans': 1, 'bikes': 1, 'third_party': 0}


class ReportTypeApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))

        delivered = StatusOption.objects.get(name='Delivered Successfully')
        # 2 TEMU (1 delivered) and 3 Base.
        change_status(create_shipment('3034001', first_seen_date=MON), delivered, effective_date=MON)
        create_shipment('3034002', first_seen_date=MON)
        for waybill in ('1001', '1002', '1003'):
            create_shipment(waybill, first_seen_date=MON, shipment_type=TYPE_BASE)

    def test_each_type_has_its_own_figures(self):
        temu = self.client.get(URL + '?type=temu').json()
        base = self.client.get(URL + '?type=base').json()

        self.assertEqual(temu['report']['shipment_type'], 'temu')
        self.assertEqual(temu['preview']['figures']['inbound'], 2)
        self.assertEqual(temu['preview']['figures']['delivered'], 1)
        self.assertEqual(base['report']['shipment_type'], 'base')
        self.assertEqual(base['preview']['figures']['inbound'], 3)
        self.assertEqual(base['preview']['figures']['delivered'], 0)

    def test_no_type_means_temu(self):
        body = self.client.get(URL).json()
        self.assertEqual(body['report']['shipment_type'], 'temu')

    def test_bad_type_is_refused(self):
        response = self.client.get(URL + '?type=parcel')
        self.assertEqual(response.status_code, 400)

    def test_transport_is_saved_per_type(self):
        self.client.patch(URL + '?type=base', {'vans': 4}, format='json')
        self.assertEqual(self.client.get(URL + '?type=base').json()['report']['vans'], 4)
        self.assertIsNone(self.client.get(URL + '?type=temu').json()['report']['vans'])

    def test_finalize_and_download_one_type(self):
        self.client.patch(URL + '?type=base', TRANSPORT, format='json')
        response = self.client.post(URL + 'finalize/?type=base', {'accept_warnings': True}, format='json')
        self.assertEqual(response.json()['state'], 'finalized')

        # TEMU is still a draft.
        self.assertEqual(self.client.get(URL + '?type=temu').json()['state'], 'draft')

        download = self.client.get(URL + 'download/?type=base')
        self.assertEqual(download.status_code, 200)
        self.assertIn('_Base_', download['Content-Disposition'])
        self.assertEqual(self.client.get(URL + 'download/?type=temu').status_code, 400)

    def test_correction_is_per_type(self):
        self.client.patch(URL + '?type=base', TRANSPORT, format='json')
        self.client.post(URL + 'finalize/?type=base', {'accept_warnings': True}, format='json')

        response = self.client.post(URL + 'correct/?type=base', {'reason': 'Vans wrong'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['report']['shipment_type'], 'base')
        self.assertEqual(response.json()['report']['version'], 2)

    def test_history_can_be_filtered_by_type(self):
        for t in ('base', 'temu'):
            self.client.patch(URL + f'?type={t}', TRANSPORT, format='json')
            self.client.post(URL + f'finalize/?type={t}', {'accept_warnings': True}, format='json')

        self.assertEqual(self.client.get('/api/reports/').json()['count'], 2)
        base_only = self.client.get('/api/reports/?type=base').json()
        self.assertEqual(base_only['count'], 1)
        self.assertEqual(base_only['results'][0]['shipment_type'], 'base')

    def test_day_shipments_are_per_type(self):
        base = self.client.get(URL + 'shipments/?type=base').json()
        self.assertEqual(base['count'], 3)
        self.assertTrue(all(r['shipment']['shipment_type'] == 'base' for r in base['results']))


class ShipmentAndImportTypeApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))

    def test_shipment_list_can_be_filtered_by_type(self):
        create_shipment('3034001', first_seen_date=MON)
        create_shipment('1001', first_seen_date=MON, shipment_type=TYPE_BASE)

        body = self.client.get('/api/shipments/?type=base').json()
        self.assertEqual([s['waybill_number'] for s in body['results']], ['1001'])

    def test_preview_shows_counts_by_type(self):
        upload = SimpleUploadedFile('scan.xlsx', make_xlsx([['3034001'], ['1001'], ['000123']]).getvalue())
        body = self.client.post('/api/imports/preview/', {'file': upload}, format='multipart').json()
        self.assertEqual(body['new_by_type'], {'base': 1, 'temu': 1, 'unknown': 1})

    def test_confirm_with_unknown_prefix_needs_a_choice(self):
        data = make_xlsx([['3034001'], ['000123']]).getvalue()

        response = self.client.post('/api/imports/confirm/', {
            'file': SimpleUploadedFile('scan.xlsx', data), 'reporting_date': str(MON),
        }, format='multipart')
        self.assertEqual(response.status_code, 400)

        response = self.client.post('/api/imports/confirm/', {
            'file': SimpleUploadedFile('scan.xlsx', data), 'reporting_date': str(MON),
            'unknown_type': 'base',
        }, format='multipart')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['base_new_count'], 1)
        self.assertEqual(response.json()['temu_new_count'], 1)
        self.assertEqual(Shipment.objects.get(waybill_number='000123').shipment_type, TYPE_BASE)

    def test_bad_unknown_choice_is_refused(self):
        upload = SimpleUploadedFile('scan.xlsx', make_xlsx([['3034001']]).getvalue())
        response = self.client.post('/api/imports/confirm/', {
            'file': upload, 'reporting_date': str(MON), 'unknown_type': 'banana',
        }, format='multipart')
        self.assertEqual(response.status_code, 400)