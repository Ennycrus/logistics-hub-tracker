"""
Tests for undoing an import.

Run with:  python manage.py test shipments
"""

import datetime
from io import BytesIO

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import StatusOption
from reports.models import DailyShipmentRecord
from reports.services.day_service import open_or_refresh_day
from reports.services.report_service import finalize, get_or_create_draft, save_draft

from .models import ImportBatch, Shipment, StatusHistory
from .services.import_service import confirm_import, undo_import
from .services.status_service import change_status, create_shipment
from .test_excel_reader import make_xlsx

MON = datetime.date(2026, 10, 26)
TUE = datetime.date(2026, 10, 27)


class UndoImportTests(TestCase):

    def test_removes_the_import_and_the_shipments_it_created(self):
        batch = confirm_import(make_xlsx([['3034000001'], ['1000000001']]), reporting_date=MON)
        open_or_refresh_day(MON)  # the open day lists the shipments

        self.assertEqual(undo_import(batch), 2)
        self.assertEqual(Shipment.objects.count(), 0)
        self.assertEqual(StatusHistory.objects.count(), 0)
        self.assertEqual(ImportBatch.objects.count(), 0)
        self.assertEqual(DailyShipmentRecord.objects.count(), 0)

    def test_shipments_already_in_the_system_are_kept(self):
        create_shipment('3034000001', first_seen_date=MON)
        batch = confirm_import(make_xlsx([['3034000001'], ['3034000002']]), reporting_date=TUE)

        self.assertEqual(undo_import(batch), 1)
        self.assertEqual(list(Shipment.objects.values_list('waybill_number', flat=True)), ['3034000001'])

    def test_refused_when_a_status_was_updated(self):
        batch = confirm_import(make_xlsx([['3034000001']]), reporting_date=MON)
        change_status(Shipment.objects.get(), StatusOption.objects.get(name='Delivered Successfully'),
                      effective_date=MON)

        with self.assertRaises(ValidationError):
            undo_import(batch)
        self.assertEqual(Shipment.objects.count(), 1)  # nothing deleted

    def test_refused_when_in_a_finalized_report(self):
        batch = confirm_import(make_xlsx([['3034000001'], ['3034000002']]), reporting_date=MON)
        finalize(save_draft(get_or_create_draft(MON), vans=1, bikes=1, third_party=0), accept_warnings=True)

        with self.assertRaises(ValidationError) as caught:
            undo_import(batch)
        message = ' '.join(caught.exception.messages)
        self.assertIn('finalized report', message)
        self.assertEqual(message.count('26 Oct 2026'), 1)  # each date listed once
        self.assertEqual(ImportBatch.objects.count(), 1)

    def test_refused_when_a_later_import_uses_its_shipments(self):
        first = confirm_import(make_xlsx([['3034000001']]), reporting_date=MON)
        confirm_import(make_xlsx([['3034000001'], ['3034000002']]), reporting_date=TUE)

        with self.assertRaises(ValidationError):
            undo_import(first)

    def test_same_file_can_be_imported_again_after_undo(self):
        data = make_xlsx([['3034000001']]).getvalue()
        undo_import(confirm_import(BytesIO(data), reporting_date=MON))
        batch = confirm_import(BytesIO(data), reporting_date=MON)
        self.assertEqual(batch.new_count, 1)


class UndoImportApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))

    def upload(self):
        file = SimpleUploadedFile('scan.xlsx', make_xlsx([['3034000001'], ['1000000001']]).getvalue())
        return self.client.post('/api/imports/confirm/', {'file': file, 'reporting_date': str(MON)},
                                format='multipart').json()

    def test_delete_undoes_the_import(self):
        batch = self.upload()
        response = self.client.delete(f'/api/imports/{batch["id"]}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['removed_shipments'], 2)
        self.assertEqual(Shipment.objects.count(), 0)

    def test_refusal_explains_why(self):
        batch = self.upload()
        change_status(Shipment.objects.first(), StatusOption.objects.get(name='Delivered Successfully'))
        response = self.client.delete(f'/api/imports/{batch["id"]}/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('cannot be undone', response.json()['error'])
        self.assertEqual(Shipment.objects.count(), 2)