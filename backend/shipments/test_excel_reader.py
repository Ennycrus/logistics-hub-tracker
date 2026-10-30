"""
Tests for the Excel reader (preview only, nothing is saved).

Run with:  python manage.py test shipments

Each test builds a small spreadsheet in memory, so no real files are needed.
"""

import datetime
from io import BytesIO

from django.core.exceptions import ValidationError
from django.test import TestCase
from openpyxl import Workbook

from core.models import StatusOption

from .models import Shipment
from .services.excel_reader import preview_scan_file
from .services.status_service import change_status, create_shipment


def make_xlsx(rows, text_cells=True):
    """Build an .xlsx file in memory from a list of rows."""
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    if text_cells:
        # Store every cell as text, like Excel does when a column is formatted as Text.
        for row in sheet.iter_rows():
            for cell in row:
                cell.number_format = '@'
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


class ExcelReaderTests(TestCase):

    def test_reads_file_with_waybill_header(self):
        file = make_xlsx([['Waybill Number'], ['TEMU001'], ['TEMU002'], ['TEMU003']])
        result = preview_scan_file(file)

        self.assertTrue(result['has_header'])
        self.assertEqual(result['selected_column'], 0)
        self.assertEqual(result['total_rows'], 3)
        self.assertEqual(result['counts']['new'], 3)

    def test_reads_file_without_header(self):
        file = make_xlsx([['TEMU001'], ['TEMU002']])
        result = preview_scan_file(file)

        self.assertFalse(result['has_header'])
        self.assertEqual(result['total_rows'], 2)

    def test_finds_waybill_column_among_several(self):
        file = make_xlsx([['No.', 'Tracking No', 'Time'], [1, 'TEMU001', '08:00']])
        result = preview_scan_file(file)
        self.assertEqual(result['selected_column'], 1)

    def test_asks_for_column_when_it_cannot_tell(self):
        file = make_xlsx([['A1', 'TEMU001'], ['A2', 'TEMU002']])
        result = preview_scan_file(file)

        self.assertIsNone(result['selected_column'])
        self.assertEqual(result['rows'], [])

    def test_chosen_column_is_used(self):
        file = make_xlsx([['A1', 'TEMU001'], ['A2', 'TEMU002']])
        result = preview_scan_file(file, column_index=1)
        self.assertEqual([r['waybill'] for r in result['rows']], ['TEMU001', 'TEMU002'])

    def test_column_that_does_not_exist_is_rejected(self):
        file = make_xlsx([['TEMU001']])
        with self.assertRaises(ValidationError):
            preview_scan_file(file, column_index=5)

    def test_leading_zeros_are_kept(self):
        file = make_xlsx([['Waybill'], ['000123']])
        result = preview_scan_file(file)
        self.assertEqual(result['rows'][0]['waybill'], '000123')

    def test_number_cells_have_no_decimal_point(self):
        file = make_xlsx([['Waybill'], [123456789.0]], text_cells=False)
        result = preview_scan_file(file)
        self.assertEqual(result['rows'][0]['waybill'], '123456789')

    def test_duplicate_inside_file_is_flagged(self):
        file = make_xlsx([['Waybill'], ['TEMU001'], ['TEMU002'], ['TEMU001']])
        result = preview_scan_file(file)

        self.assertEqual(result['counts']['new'], 2)
        self.assertEqual(result['counts']['duplicate_in_file'], 1)
        self.assertEqual(result['rows'][2]['result'], 'duplicate_in_file')

    def test_empty_and_bad_waybills_are_invalid(self):
        file = make_xlsx([['Waybill', 'Note'], [None, 'missed scan'], ['TEMU 01', ''], ['OK001', '']])
        result = preview_scan_file(file)

        self.assertEqual(result['counts']['invalid'], 2)
        self.assertEqual(result['counts']['new'], 1)

    def test_blank_rows_are_skipped(self):
        file = make_xlsx([['Waybill'], ['TEMU001'], [None], ['TEMU002']])
        result = preview_scan_file(file)
        self.assertEqual(result['total_rows'], 2)

    def test_existing_outstanding_and_closed_are_told_apart(self):
        monday = datetime.date(2026, 10, 26)
        create_shipment('OPEN001', first_seen_date=monday)  # still unchecked
        closed = create_shipment('DONE001', first_seen_date=monday)
        change_status(closed, StatusOption.objects.get(name='Delivered Successfully'))

        file = make_xlsx([['Waybill'], ['OPEN001'], ['DONE001'], ['NEW001']])
        result = preview_scan_file(file)

        outcomes = {r['waybill']: r['result'] for r in result['rows']}
        self.assertEqual(outcomes, {
            'OPEN001': 'existing_outstanding',
            'DONE001': 'existing_closed',
            'NEW001': 'new',
        })

    def test_preview_saves_nothing(self):
        file = make_xlsx([['Waybill'], ['TEMU001'], ['TEMU002']])
        preview_scan_file(file)
        self.assertEqual(Shipment.objects.count(), 0)

    def test_non_excel_file_is_rejected(self):
        with self.assertRaises(ValidationError):
            preview_scan_file(BytesIO(b'this is not a spreadsheet'))

    def test_empty_spreadsheet_is_rejected(self):
        with self.assertRaises(ValidationError):
            preview_scan_file(make_xlsx([]))