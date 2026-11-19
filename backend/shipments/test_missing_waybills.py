"""
Tests that no waybill in a scanner file is skipped silently:
  - several waybills in one cell are all read
  - waybills in other columns are reported, and can be imported too
  - formula cells with no saved value are reported

Run with:  python manage.py test shipments.test_missing_waybills
"""

import datetime
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook
from rest_framework.test import APIClient

from .models import ImportBatch, Shipment
from .services.excel_reader import preview_scan_file
from .services.import_service import confirm_import
from .test_excel_reader import make_xlsx

MON = datetime.date(2026, 10, 26)
T1, T2, T3, T4 = '303400000001', '303400000002', '303400000003', '303400000004'
B1 = '1000000001'


class MissingWaybillTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))

    def waybills(self, result):
        return [r['waybill'] for r in result['rows']]

    # --- Several waybills in one cell ---------------------------------------

    def test_several_waybills_in_one_cell_are_all_read(self):
        result = preview_scan_file(make_xlsx([['Waybill'], [f'{T1}\n{T2}'], [f'{T3}, {T4}'], [B1]]))
        self.assertEqual(self.waybills(result), [T1, T2, T3, T4, B1])
        self.assertEqual(result['counts']['new'], 5)
        self.assertEqual(result['waybills_found'], 5)
        self.assertEqual(result['total_rows'], 3)

    def test_text_with_spaces_is_still_invalid(self):
        result = preview_scan_file(make_xlsx([['Waybill'], ['TEMU 01']]))
        self.assertEqual(result['counts']['invalid'], 1)

    # --- Waybills in other columns ------------------------------------------

    def other_columns_file(self):
        return make_xlsx([
            ['Waybill', 'Second scan', 'Rider phone', 'Amount'],
            [T1, T2, '08012345678', '1500'],
            [T3, '', '08099999999', '2000'],
            ['', T4, '', ''],
        ])

    def test_waybills_in_other_columns_are_reported_not_imported(self):
        result = preview_scan_file(self.other_columns_file())
        self.assertEqual(self.waybills(result), [T1, T3, ''])
        self.assertEqual(result['elsewhere'], [{'column': 'Second scan', 'count': 2}])  # not phones or amounts

    def test_all_columns_imports_them_too(self):
        result = preview_scan_file(self.other_columns_file(), all_columns=True)
        self.assertEqual(sorted(self.waybills(result)), [T1, T2, T3, T4])
        self.assertEqual(result['counts']['new'], 4)
        self.assertEqual(result['counts']['invalid'], 0)  # the empty first cell of row 3 is not counted
        self.assertEqual(result['elsewhere'], [])

    def test_all_columns_import_after_a_one_column_import(self):
        data = self.other_columns_file().getvalue()
        first = confirm_import(BytesIO(data), reporting_date=MON)
        self.assertEqual(first.new_count, 2)
        # The same file again, all columns: allowed once, picks up only the missing ones.
        second = confirm_import(BytesIO(data), reporting_date=MON, all_columns=True)
        self.assertEqual((second.new_count, second.existing_outstanding_count), (2, 2))
        self.assertEqual(Shipment.objects.count(), 4)
        self.assertEqual(ImportBatch.objects.count(), 2)

    def test_all_columns_through_the_api(self):
        upload = SimpleUploadedFile('scan.xlsx', self.other_columns_file().getvalue())
        preview = self.client.post('/api/imports/preview/', {'file': upload, 'all_columns': 'true'},
                                   format='multipart').json()
        self.assertEqual(preview['counts']['new'], 4)
        upload = SimpleUploadedFile('scan.xlsx', self.other_columns_file().getvalue())
        response = self.client.post('/api/imports/confirm/', {
            'file': upload, 'reporting_date': MON.isoformat(), 'all_columns': 'true',
        }, format='multipart')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['new_count'], 4)

    # --- Formulas with no saved value ----------------------------------------

    def test_formula_cells_without_a_value_are_counted(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['Waybill'])
        sheet.append([T1])
        sheet.append(['=CONCATENATE("3034","00000009")'])  # saved by a script: no result stored
        file = BytesIO()
        workbook.save(file)
        file.seek(0)
        result = preview_scan_file(file)
        self.assertEqual(result['formulas_without_value'], 1)
        self.assertEqual(self.waybills(result), [T1])

    def test_normal_file_has_no_warnings(self):
        result = preview_scan_file(make_xlsx([['Waybill'], [T1], [T2]]))
        self.assertEqual((result['formulas_without_value'], result['elsewhere']), (0, []))