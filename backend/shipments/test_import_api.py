"""
Tests for the import API (upload, preview, confirm, history).

Run with:  python manage.py test shipments
"""

import datetime

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import ImportBatch, Shipment
from .serializers import MAX_UPLOAD_BYTES
from .test_excel_reader import make_xlsx

MON = datetime.date(2026, 10, 26)

# Real-looking TEMU waybills (they start with 3034).
W1, W2 = '303400000001', '303400000002'


def upload(rows, name='scan.xlsx'):
    """An uploaded .xlsx file, like the browser would send."""
    return SimpleUploadedFile(name, make_xlsx(rows).getvalue())


class ImportApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))

    def test_preview_classifies_rows_and_saves_nothing(self):
        response = self.client.post(
            '/api/imports/preview/', {'file': upload([[W1], [W2], [W1]])}, format='multipart',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['counts']['new'], 2)
        self.assertEqual(body['counts']['duplicate_in_file'], 1)
        self.assertIsNone(body['already_imported'])
        self.assertEqual(Shipment.objects.count(), 0)

    def test_preview_asks_for_column_when_unclear(self):
        response = self.client.post(
            '/api/imports/preview/', {'file': upload([['x', W1], ['y', W2]])}, format='multipart',
        )
        self.assertIsNone(response.json()['selected_column'])

        response = self.client.post(
            '/api/imports/preview/', {'file': upload([['x', W1], ['y', W2]]), 'column': 1},
            format='multipart',
        )
        self.assertEqual(response.json()['counts']['new'], 2)

    def test_confirm_creates_batch_and_shipments(self):
        response = self.client.post(
            '/api/imports/confirm/',
            {'file': upload([[W1], [W2]]), 'reporting_date': str(MON)},
            format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['new_count'], 2)
        self.assertEqual(Shipment.objects.count(), 2)

    def test_same_file_twice_is_refused(self):
        # Same bytes every time (see the note in test_import_service.py).
        data = make_xlsx([[W1], [W2]]).getvalue()

        def same_file():
            return SimpleUploadedFile('scan.xlsx', data)

        self.client.post('/api/imports/confirm/',
                         {'file': same_file(), 'reporting_date': str(MON)}, format='multipart')

        preview = self.client.post('/api/imports/preview/', {'file': same_file()}, format='multipart')
        self.assertIsNotNone(preview.json()['already_imported'])

        response = self.client.post('/api/imports/confirm/',
                                    {'file': same_file(), 'reporting_date': str(MON)}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('already imported', response.json()['error'])
        self.assertEqual(ImportBatch.objects.count(), 1)

    def test_confirm_needs_a_date(self):
        response = self.client.post('/api/imports/confirm/', {'file': upload([['A1']])}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('reporting_date', response.json()['details'])

    def test_future_date_is_refused(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        response = self.client.post(
            '/api/imports/confirm/', {'file': upload([['A1']]), 'reporting_date': str(tomorrow)},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)

    def test_wrong_file_type_is_refused(self):
        response = self.client.post(
            '/api/imports/preview/', {'file': SimpleUploadedFile('scan.csv', b'A1\nA2')},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('.xlsx', response.json()['error'])

    def test_broken_excel_file_is_refused(self):
        response = self.client.post(
            '/api/imports/preview/', {'file': SimpleUploadedFile('scan.xlsx', b'not really excel')},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('not a valid Excel', response.json()['error'])

    def test_oversized_file_is_refused(self):
        big = SimpleUploadedFile('scan.xlsx', b'0' * (MAX_UPLOAD_BYTES + 1))
        response = self.client.post('/api/imports/preview/', {'file': big}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('too large', response.json()['error'])

    def test_import_history_and_detail(self):
        self.client.post('/api/imports/confirm/',
                         {'file': upload([[W1], [W1]]), 'reporting_date': str(MON)},
                         format='multipart')

        history = self.client.get('/api/imports/').json()
        self.assertEqual(history['count'], 1)

        batch_id = history['results'][0]['id']
        detail = self.client.get(f'/api/imports/{batch_id}/').json()
        self.assertEqual([r['result'] for r in detail['rows']], ['new', 'duplicate_in_file'])