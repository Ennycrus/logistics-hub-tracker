"""
Tests for Base / TEMU detection and the type check when creating shipments.

Run with:  python manage.py test shipments
"""

import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import TYPE_BASE, TYPE_TEMU
from .services.excel_reader import preview_scan_file
from .services.shipment_types import detect_type
from .services.status_service import create_shipment
from .test_excel_reader import make_xlsx

MON = datetime.date(2026, 10, 26)


class DetectTypeTests(TestCase):

    def test_temu_prefix(self):
        self.assertEqual(detect_type('303491573584'), TYPE_TEMU)

    def test_base_prefix(self):
        self.assertEqual(detect_type('1234567890'), TYPE_BASE)

    def test_unknown_prefix(self):
        self.assertIsNone(detect_type('2034000'))
        self.assertIsNone(detect_type('000123'))
        self.assertIsNone(detect_type(''))

    def test_spaces_are_ignored(self):
        self.assertEqual(detect_type('  3034111 '), TYPE_TEMU)


class CreateShipmentTypeTests(TestCase):

    def test_type_is_saved(self):
        shipment = create_shipment('1000001', first_seen_date=MON, shipment_type=TYPE_BASE)
        self.assertEqual(shipment.shipment_type, TYPE_BASE)

    def test_type_that_contradicts_the_prefix_is_refused(self):
        with self.assertRaises(ValidationError):
            create_shipment('1000001', first_seen_date=MON, shipment_type=TYPE_TEMU)
        with self.assertRaises(ValidationError):
            create_shipment('3034000001', first_seen_date=MON, shipment_type=TYPE_BASE)

    def test_unknown_type_value_is_refused(self):
        with self.assertRaises(ValidationError):
            create_shipment('000123', first_seen_date=MON, shipment_type='parcel')


class PreviewTypeTests(TestCase):

    def test_preview_counts_new_shipments_by_type(self):
        result = preview_scan_file(make_xlsx([['3034000001'], ['1000001'], ['1000002'], ['000123']]))
        self.assertEqual(result['new_by_type'], {'base': 2, 'temu': 1, 'unknown': 1})
        self.assertEqual([r['shipment_type'] for r in result['rows']], ['temu', 'base', 'base', None])

    def test_existing_shipment_keeps_its_type(self):
        create_shipment('000123', first_seen_date=MON, shipment_type=TYPE_BASE)
        row = preview_scan_file(make_xlsx([['000123']]))['rows'][0]
        self.assertEqual(row['result'], 'existing_outstanding')
        self.assertEqual(row['shipment_type'], TYPE_BASE)