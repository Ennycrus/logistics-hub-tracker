"""
Tests for the shipments Excel export (same filters as the list).

Run with:  python manage.py test shipments.test_export
"""

import datetime
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from openpyxl import load_workbook
from rest_framework.test import APIClient

from core.models import StatusOption
from .services.status_service import change_status, create_shipment

MON = datetime.date(2026, 11, 2)


class ExportTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        self.delivered = StatusOption.objects.get(name='Delivered Successfully')
        self.pending = StatusOption.objects.get(name='Pending Delivery')
        change_status(create_shipment('303400000001', first_seen_date=MON), self.delivered, effective_date=MON)
        change_status(create_shipment('303400000002', first_seen_date=MON), self.pending, effective_date=MON)

    def rows(self, query=''):
        resp = self.client.get(f'/api/shipments/export/{query}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])
        self.assertIn('attachment', resp['Content-Disposition'])
        wb = load_workbook(BytesIO(resp.content))
        ws = wb.active
        return [[c.value for c in row] for row in ws.iter_rows()]

    def test_export_has_header_and_a_row_per_shipment(self):
        rows = self.rows()
        self.assertEqual(rows[0][0], 'Waybill Number')
        waybills = {r[0] for r in rows[1:]}
        self.assertEqual(waybills, {'303400000001', '303400000002'})

    def test_export_respects_filters(self):
        rows = self.rows('?category=delivered')
        waybills = {r[0] for r in rows[1:]}
        self.assertEqual(waybills, {'303400000001'})
        # delivered_on column is filled for the delivered one
        header = rows[0]
        idx = header.index('Delivered on')
        self.assertEqual(rows[1][idx], '2026-11-02')

    def test_formula_like_note_stays_text(self):
        s = create_shipment('303400000003', first_seen_date=MON)
        s.notes = '=danger()'
        s.save()
        rows = self.rows('?search=303400000003')
        self.assertIn('=danger()', [c for r in rows for c in r])