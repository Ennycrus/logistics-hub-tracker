"""
Tests for reading every row of a scanner file, and for importing a list
pasted from Google Sheets.

Run with:  python manage.py test shipments.test_paste_import
"""

import datetime
import re
import zipfile
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook
from rest_framework.test import APIClient

from .models import ImportBatch, Shipment
from .services.excel_reader import preview_scan_file

MON = datetime.date(2026, 10, 26)


def xlsx_with_wrong_size(count, claimed_rows):
    """An .xlsx with `count` waybills whose saved size claims only `claimed_rows` rows."""
    workbook = Workbook()
    for n in range(1, count + 1):
        workbook.active.cell(row=n, column=1, value=f'3034{n:08d}')
    good = BytesIO()
    workbook.save(good)

    broken = BytesIO()
    with zipfile.ZipFile(good) as source, zipfile.ZipFile(broken, 'w') as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == 'xl/worksheets/sheet1.xml':
                data = re.sub(rb'<dimension ref="[^"]+"/>', f'<dimension ref="A1:A{claimed_rows}"/>'.encode(), data)
            target.writestr(item, data)
    broken.seek(0)
    return broken


class ReadEveryRowTests(TestCase):

    def test_wrong_saved_size_does_not_drop_rows(self):
        result = preview_scan_file(xlsx_with_wrong_size(200, claimed_rows=50))
        self.assertEqual(result['total_rows'], 200)
        self.assertEqual(result['counts']['new'], 200)

    def test_other_sheets_with_data_are_reported(self):
        workbook = Workbook()
        workbook.active.title = 'Monday'
        workbook.active.append(['303400000001'])
        workbook.create_sheet('Tuesday').append(['303400000002'])
        workbook.create_sheet('Empty')
        file = BytesIO()
        workbook.save(file)
        file.seek(0)
        result = preview_scan_file(file)
        self.assertEqual(result['total_rows'], 1)
        self.assertEqual(result['other_sheets'], ['Tuesday'])

    def test_single_sheet_reports_no_other_sheets(self):
        result = preview_scan_file(xlsx_with_wrong_size(3, claimed_rows=3))
        self.assertEqual(result['other_sheets'], [])


class PastedListTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))

    def paste(self, text, name='Pasted list.txt'):
        return SimpleUploadedFile(name, text.encode(), content_type='text/plain')

    def test_pasted_column_is_previewed(self):
        text = '303400000001\r\n303400000002\r\n\r\n100000000001\r\n303400000001\r\n'
        response = self.client.post('/api/imports/preview/', {'file': self.paste(text)}, format='multipart')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['total_rows'], 4)  # the blank line is skipped
        self.assertEqual(body['counts']['new'], 3)
        self.assertEqual(body['counts']['duplicate_in_file'], 1)
        self.assertEqual(body['new_by_type'], {'temu': 2, 'base': 1, 'unknown': 0})
        self.assertEqual(Shipment.objects.count(), 0)  # preview saves nothing

    def test_pasted_cells_with_a_header_row(self):
        text = 'Date\tWaybill Number\n18/11\t303400000001\n18/11\t303400000002\n'
        result = preview_scan_file(BytesIO(text.encode()), file_name='Pasted list.txt')
        self.assertTrue(result['has_header'])
        self.assertEqual(result['selected_column'], 1)
        self.assertEqual([r['waybill'] for r in result['rows']], ['303400000001', '303400000002'])

    def test_csv_file(self):
        result = preview_scan_file(BytesIO(b'Waybill\n303400000001\n303400000002\n'), file_name='scan.csv')
        self.assertEqual(result['counts']['new'], 2)

    def test_pasted_list_is_imported(self):
        text = '303400000001\n303400000002\n'
        response = self.client.post('/api/imports/confirm/', {
            'file': self.paste(text), 'reporting_date': MON.isoformat(),
        }, format='multipart')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['new_count'], 2)
        self.assertEqual(ImportBatch.objects.get().file_name, 'Pasted list.txt')
        self.assertEqual(Shipment.objects.count(), 2)

    def test_same_paste_twice_is_refused(self):
        text = '303400000001\n'
        for expected in (201, 400):
            response = self.client.post('/api/imports/confirm/', {
                'file': self.paste(text), 'reporting_date': MON.isoformat(),
            }, format='multipart')
            self.assertEqual(response.status_code, expected)
        self.assertIn('already imported', response.json()['error'])

    def test_other_file_types_are_refused(self):
        response = self.client.post(
            '/api/imports/preview/', {'file': SimpleUploadedFile('scan.pdf', b'x')}, format='multipart',
        )
        self.assertEqual(response.status_code, 400)