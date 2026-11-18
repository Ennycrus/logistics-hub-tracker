"""
Tests for hiding delivered shipments on the Shipments page.

Run with:  python manage.py test shipments.test_hide_delivered
"""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import StatusOption

from .services.status_service import change_status, create_shipment

MON = datetime.date(2026, 10, 26)


class HideDeliveredTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        delivered = StatusOption.objects.get(name='Delivered Successfully')
        create_shipment('303400000001', first_seen_date=MON)
        done = create_shipment('303400000002', first_seen_date=MON)
        change_status(done, delivered, effective_date=MON, delivered_by='rider')

    def waybills(self, query=''):
        response = self.client.get(f'/api/shipments/{query}')
        self.assertEqual(response.status_code, 200)
        return [s['waybill_number'] for s in response.json()['results']]

    def test_delivered_are_hidden_when_asked(self):
        self.assertEqual(self.waybills('?hide_delivered=1'), ['303400000001'])

    def test_everything_is_shown_by_default(self):
        self.assertEqual(self.waybills(), ['303400000001', '303400000002'])

    def test_delivered_filter_still_works(self):
        self.assertEqual(self.waybills('?category=delivered'), ['303400000002'])