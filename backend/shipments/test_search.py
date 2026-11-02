"""
Tests for waybill search: 4 digits = last four, anything else = contains.

Run with:  python manage.py test shipments
"""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .services.status_service import create_shipment

MON = datetime.date(2026, 10, 26)


class WaybillSearchTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        create_shipment('303491573584', first_seen_date=MON)  # ends with 3584
        create_shipment('303435840012', first_seen_date=MON)  # has 3584 in the middle

    def found(self, url):
        return sorted(r['waybill_number'] if 'waybill_number' in r else r['shipment']['waybill_number']
                      for r in self.client.get(url).json()['results'])

    def test_four_digits_match_the_end_only(self):
        self.assertEqual(self.found('/api/shipments/?search=3584'), ['303491573584'])

    def test_other_searches_match_anywhere(self):
        self.assertEqual(self.found('/api/shipments/?search=35840'), ['303435840012'])
        self.assertEqual(self.found('/api/shipments/?search=3034'), [])  # 4 digits: an ending, not a start
        self.assertEqual(self.found('/api/shipments/?search=30349'), ['303491573584'])

    def test_spaces_are_ignored(self):
        self.assertEqual(self.found('/api/shipments/?search=%203584%20'), ['303491573584'])

    def test_report_shipments_use_the_same_rule(self):
        self.assertEqual(self.found(f'/api/reports/{MON}/shipments/?kind=inbound&search=3584'), ['303491573584'])