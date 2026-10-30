"""
Tests for confirming an import (this one DOES save to the database).

Run with:  python manage.py test shipments

Waybills follow the real rules: TEMU starts with 3034, Base starts with 1.
"""

import datetime
from io import BytesIO

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import StatusOption

from .models import TYPE_BASE, TYPE_TEMU, ImportBatch, ImportRow, Shipment, StatusHistory
from .services.import_service import confirm_import
from .services.status_service import change_status, create_shipment
from .test_excel_reader import make_xlsx

MONDAY = datetime.date(2026, 10, 26)
TUESDAY = datetime.date(2026, 10, 27)

T1, T2, T3 = '303400000001', '303400000002', '303400000003'   # TEMU
B1, B2 = '100000000001', '100000000002'                       # Base


class ImportServiceTests(TestCase):

    def test_import_creates_batch_and_new_shipments(self):
        file = make_xlsx([[T1], [T2], [T3]])
        batch = confirm_import(file, reporting_date=MONDAY, file_name='mon.xlsx')

        self.assertEqual(batch.total_rows, 3)
        self.assertEqual(batch.new_count, 3)
        self.assertEqual(batch.temu_new_count, 3)
        self.assertEqual(batch.rows.count(), 3)
        self.assertEqual(Shipment.objects.count(), 3)

        shipment = Shipment.objects.get(waybill_number=T1)
        self.assertEqual(shipment.status.category, StatusOption.CATEGORY_UNCHECKED)
        self.assertEqual(shipment.first_seen_date, MONDAY)
        self.assertEqual(shipment.history.count(), 1)  # created by the service

    def test_type_comes_from_the_waybill_prefix(self):
        batch = confirm_import(make_xlsx([[T1], [B1], [B2]]), reporting_date=MONDAY)

        self.assertEqual(batch.base_new_count, 2)
        self.assertEqual(batch.temu_new_count, 1)
        self.assertEqual(Shipment.objects.get(waybill_number=T1).shipment_type, TYPE_TEMU)
        self.assertEqual(Shipment.objects.get(waybill_number=B1).shipment_type, TYPE_BASE)

    def test_unknown_prefix_needs_a_choice(self):
        file = make_xlsx([[T1], ['000123']]).getvalue()
        with self.assertRaises(ValidationError):
            confirm_import(BytesIO(file), reporting_date=MONDAY)
        self.assertEqual(Shipment.objects.count(), 0)  # nothing saved

    def test_unknown_prefix_can_be_given_a_type(self):
        confirm_import(make_xlsx([['000123']]), reporting_date=MONDAY, unknown_type='base')
        self.assertEqual(Shipment.objects.get(waybill_number='000123').shipment_type, TYPE_BASE)

    def test_unknown_prefix_can_be_skipped(self):
        batch = confirm_import(make_xlsx([[T1], ['000123']]), reporting_date=MONDAY, unknown_type='skip')

        self.assertEqual(batch.new_count, 1)
        self.assertEqual(batch.invalid_count, 1)
        self.assertFalse(Shipment.objects.filter(waybill_number='000123').exists())
        self.assertIn('Skipped', batch.rows.get(waybill_number='000123').message)

    def test_bad_unknown_choice_is_refused(self):
        with self.assertRaises(ValidationError):
            confirm_import(make_xlsx([[T1]]), reporting_date=MONDAY, unknown_type='banana')

    def test_same_file_cannot_be_imported_twice(self):
        # Build the file ONCE and upload the same bytes twice. (Two files built
        # a second apart differ, because Excel files store their creation time.)
        data = make_xlsx([[T1], [T2]]).getvalue()
        confirm_import(BytesIO(data), reporting_date=MONDAY)

        with self.assertRaises(ValidationError):
            confirm_import(BytesIO(data), reporting_date=TUESDAY)
        self.assertEqual(ImportBatch.objects.count(), 1)

    def test_duplicates_and_invalid_rows_create_no_shipments(self):
        file = make_xlsx([['Waybill'], [T1], [T1], [None, 'x'], ['BAD ONE']])
        batch = confirm_import(file, reporting_date=MONDAY)

        self.assertEqual(batch.new_count, 1)
        self.assertEqual(batch.duplicate_in_file_count, 1)
        self.assertEqual(batch.invalid_count, 2)
        self.assertEqual(Shipment.objects.count(), 1)

    def test_outstanding_shipment_in_later_file_is_not_recreated(self):
        confirm_import(make_xlsx([[T1], [T2]]), reporting_date=MONDAY)
        tuesday = confirm_import(make_xlsx([[T1], [T3]]), reporting_date=TUESDAY)

        self.assertEqual(tuesday.new_count, 1)  # only T3
        self.assertEqual(tuesday.existing_outstanding_count, 1)  # T1
        self.assertEqual(Shipment.objects.filter(waybill_number=T1).count(), 1)

        # T1 keeps its Monday identity and is linked to Tuesday's batch.
        row = tuesday.rows.get(waybill_number=T1)
        self.assertEqual(row.shipment.first_seen_date, MONDAY)

    def test_import_does_not_change_existing_status(self):
        shipment = create_shipment(T1, first_seen_date=MONDAY)
        change_status(shipment, StatusOption.objects.get(name='Delivered Successfully'))
        history_before = StatusHistory.objects.count()

        batch = confirm_import(make_xlsx([[T1]]), reporting_date=TUESDAY)
        shipment.refresh_from_db()

        self.assertEqual(batch.existing_closed_count, 1)
        self.assertEqual(shipment.status.name, 'Delivered Successfully')
        self.assertEqual(StatusHistory.objects.count(), history_before)

    def test_unknown_column_saves_nothing(self):
        file = make_xlsx([['A1', T1], ['A2', T2]])
        with self.assertRaises(ValidationError):
            confirm_import(file, reporting_date=MONDAY)

        self.assertEqual(ImportBatch.objects.count(), 0)
        self.assertEqual(Shipment.objects.count(), 0)

    def test_chosen_column_works(self):
        file = make_xlsx([['A1', T1], ['A2', T2]])
        batch = confirm_import(file, reporting_date=MONDAY, column_index=1)
        self.assertEqual(batch.column_index, 1)
        self.assertEqual(batch.new_count, 2)

    def test_every_row_is_recorded_with_its_result(self):
        file = make_xlsx([['Waybill'], [T1], [T1]])
        batch = confirm_import(file, reporting_date=MONDAY)

        results = list(batch.rows.values_list('row_number', 'result'))
        self.assertEqual(results, [
            (2, ImportRow.RESULT_NEW),
            (3, ImportRow.RESULT_DUPLICATE_IN_FILE),
        ])