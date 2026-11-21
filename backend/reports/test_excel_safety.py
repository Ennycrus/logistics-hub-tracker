"""
Tests that text starting with "=" stays plain text in every Excel download.

Run with:  python manage.py test reports.test_excel_safety
"""

import datetime
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from openpyxl import Workbook, load_workbook
from rest_framework.test import APIClient

from core.models import HubConfig, StatusOption
from shipments.services.status_service import change_status, create_shipment

from .services.excel_export import COLUMNS, DATA_ROW, export_report_bytes
from .services.excel_safety import keep_as_text
from .services.report_service import finalize, get_or_create_draft, save_draft

MON = datetime.date(2026, 11, 9)
SAT = datetime.date(2026, 11, 14)
TRICK = '=HYPERLINK("http://example.com","click")'


def cells(data):
    """Every (value, type) in the first sheet of an .xlsx file."""
    sheet = load_workbook(BytesIO(data)).active
    return [(c.value, c.data_type) for row in sheet.iter_rows() for c in row if c.value is not None]


class ExcelSafetyTests(TestCase):

    def test_text_that_looks_like_a_formula_is_kept_as_text(self):
        workbook = Workbook()
        workbook.active['A1'] = '=1+1'
        workbook.active['A2'] = 5
        buffer = BytesIO()
        keep_as_text(workbook).save(buffer)
        self.assertEqual(cells(buffer.getvalue()), [('=1+1', 's'), (5, 'n')])

    def test_daily_report_reasons(self):
        delivered = StatusOption.objects.get(name='Delivered Successfully')
        change_status(create_shipment('303400000001', first_seen_date=MON), delivered,
                      effective_date=MON, delivered_by='rider')
        report = finalize(save_draft(get_or_create_draft(MON), vans=1, bikes=1, third_party=0,
                                     reasons_text=TRICK))
        sheet = load_workbook(BytesIO(export_report_bytes(report))).active
        reasons = sheet.cell(row=DATA_ROW, column=[k for _, k in COLUMNS].index('reasons_text') + 1)
        self.assertEqual((reasons.value, reasons.data_type), (TRICK, 's'))

    def test_saturday_report_notes_and_hub_name(self):
        config = HubConfig.get()
        config.hub_name = '=Hub'
        config.save()
        client = APIClient()
        client.force_authenticate(User.objects.create_user('tester'))
        client.post(f'/api/reports/weekly-hub/?date={SAT}', {'extra_notes': TRICK}, format='json')
        response = client.get(f'/api/reports/weekly-hub/download/?date={SAT}')
        self.assertEqual(response.status_code, 200)
        found = cells(response.content)
        self.assertIn((TRICK, 's'), found)
        self.assertNotIn('f', [kind for _, kind in found])

    def test_weekly_download_has_no_formulas(self):
        client = APIClient()
        client.force_authenticate(User.objects.create_user('tester'))
        response = client.get(f'/api/reports/weekly/download/?date={SAT}')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('f', [kind for _, kind in cells(response.content)])