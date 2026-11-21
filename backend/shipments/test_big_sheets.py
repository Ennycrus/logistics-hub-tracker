"""
Tests that a sheet far bigger than a scanner file is refused quickly instead of
keeping the server busy (e.g. a small .xlsx that unpacks to millions of empty rows).

Run with:  python manage.py test shipments.test_big_sheets
"""

import time
from io import BytesIO
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase
from openpyxl import Workbook

from .services.excel_reader import preview_scan_file
from .test_excel_reader import make_xlsx


def workbook_file(build):
    workbook = Workbook()
    build(workbook)
    file = BytesIO()
    workbook.save(file)
    file.seek(0)
    return file


class BigSheetTests(TestCase):

    def test_too_many_rows_even_if_empty(self):
        def build(workbook):
            sheet = workbook.active
            sheet['A1'] = 'Waybill'
            sheet['A2'] = '303400000001'
            sheet['A25000'] = ''  # a far-away cell: everything in between is empty
            sheet['A25001'] = 'x'
        started = time.monotonic()
        with self.assertRaisesMessage(ValidationError, 'far larger than a scanner file'):
            preview_scan_file(workbook_file(build))
        self.assertLess(time.monotonic() - started, 10)

    def test_too_many_cells(self):
        file = make_xlsx([['Waybill'] + [''] * 20] + [['303400000001'] + ['x'] * 20] * 60)
        with mock.patch('shipments.services.excel_reader.MAX_SHEET_CELLS', 1000):
            with self.assertRaisesMessage(ValidationError, 'far larger than a scanner file'):
                preview_scan_file(file)

    def test_a_huge_second_sheet_is_refused_too(self):
        def build(workbook):
            workbook.active['A1'] = '303400000001'
            other = workbook.create_sheet('Other')
            other['A30000'] = 'x'
        with self.assertRaisesMessage(ValidationError, '"Other"'):
            preview_scan_file(workbook_file(build))

    def test_normal_files_are_fine(self):
        file = make_xlsx([['Waybill']] + [[f'3034{n:08d}'] for n in range(3000)])
        self.assertEqual(preview_scan_file(file)['counts']['new'], 3000)