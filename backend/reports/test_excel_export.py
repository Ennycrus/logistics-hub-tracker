"""
Tests for the Excel export.

Run with:  python manage.py test reports
"""

import datetime
from io import BytesIO

from django.core.exceptions import ValidationError
from django.test import TestCase
from openpyxl import load_workbook

from core.models import FailureReason, HubConfig, StatusOption
from shipments.services.status_service import change_status, create_shipment

from .services.excel_export import (
    COLUMNS, DATA_ROW, HEADER_ROW, export_file_name, export_report_bytes,
)
from .services.report_service import finalize, get_or_create_draft, save_draft, start_correction

MON = datetime.date(2026, 10, 26)

EXPECTED_HEADINGS = [
    'HUBS', 'Inbound', 'Old Pending', 'Total Available', 'Delivered', 'Current Day',
    'Return', 'No of Vans', 'No of Bike', 'No of 3PL', 'Reasons',
]


class ExcelExportTests(TestCase):

    def setUp(self):
        config = HubConfig.get()
        config.hub_name = 'Akala_Express'
        config.save()

        delivered = StatusOption.objects.get(name='Delivered Successfully')
        unsuccessful = StatusOption.objects.get(name='Delivery Unsuccessful')
        unavailable = FailureReason.objects.get(name='Customer unavailable')

        change_status(create_shipment('D1', first_seen_date=MON), delivered, effective_date=MON)
        change_status(create_shipment('U1', first_seen_date=MON), unsuccessful,
                      failure_reason=unavailable, effective_date=MON)

        draft = save_draft(get_or_create_draft(MON), vans=2, bikes=6, third_party=3)
        self.report = finalize(draft)

    def open_sheet(self, report):
        workbook = load_workbook(BytesIO(export_report_bytes(report)))
        return workbook.active

    def row(self, sheet, number):
        return [sheet.cell(row=number, column=c).value for c in range(1, len(COLUMNS) + 1)]

    def test_headings_are_in_company_order(self):
        sheet = self.open_sheet(self.report)
        self.assertEqual(self.row(sheet, HEADER_ROW), EXPECTED_HEADINGS)

    def test_values_come_from_the_snapshot(self):
        sheet = self.open_sheet(self.report)
        self.assertEqual(self.row(sheet, DATA_ROW), [
            'Akala_Express', 2, 0, 2, 1, 1, 0, 2, 6, 3, 'Customer unavailable - 1',
        ])

    def test_hub_and_date_are_shown(self):
        sheet = self.open_sheet(self.report)
        self.assertEqual(sheet['A2'].value, 'Date: 26 Oct 2026')

    def test_no_waybill_numbers_in_the_report(self):
        sheet = self.open_sheet(self.report)
        all_text = ' '.join(str(c.value) for row in sheet.iter_rows() for c in row if c.value)
        self.assertNotIn('D1', all_text.split())
        self.assertNotIn('U1', all_text.split())

    def test_draft_cannot_be_exported(self):
        correction = start_correction(MON, 'Fix vans')
        with self.assertRaises(ValidationError):
            export_report_bytes(correction)

    def test_correction_is_labelled(self):
        correction = save_draft(start_correction(MON, 'Vans figure was wrong'), vans=4)
        corrected = finalize(correction)
        sheet = self.open_sheet(corrected)

        self.assertIn('version 2', sheet['A3'].value)
        self.assertEqual(sheet.cell(row=DATA_ROW, column=8).value, 4)
        self.assertEqual(export_file_name(corrected), 'Akala_Express_TEMU_2026-10-26_v2.xlsx')

    def test_file_name(self):
        self.assertEqual(export_file_name(self.report), 'Akala_Express_TEMU_2026-10-26.xlsx')

    def test_title_names_the_report_type(self):
        sheet = self.open_sheet(self.report)
        self.assertEqual(sheet['A1'].value, 'Daily Hub Report - TEMU')