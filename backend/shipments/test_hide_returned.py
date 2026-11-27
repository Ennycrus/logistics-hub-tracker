"""
Tests for hiding delivered / returned shipments on the list.

Run with:  python manage.py test shipments.test_hide_returned
"""

import datetime
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import StatusOption
from .services.status_service import change_status, create_shipment

MON = datetime.date(2026, 11, 2)


class HideReturnedTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        self.delivered = StatusOption.objects.get(name='Delivered Successfully')
        self.rerouted = StatusOption.objects.get(name='Rerouted to Another Hub')
        self.pending = StatusOption.objects.get(name='Pending Delivery')
        change_status(create_shipment('303400000001', first_seen_date=MON), self.pending, effective_date=MON)
        change_status(create_shipment('303400000002', first_seen_date=MON), self.delivered, effective_date=MON)
        change_status(create_shipment('303400000003', first_seen_date=MON), self.rerouted, effective_date=MON)

    def waybills(self, query=''):
        return {r['waybill_number'] for r in self.client.get(f'/api/shipments/{query}').json()['results']}

    def test_hide_returned_leaves_out_left_hub(self):
        self.assertEqual(self.waybills('?hide_returned=1'), {'303400000001', '303400000002'})

    def test_hide_both_shows_only_at_hub(self):
        self.assertEqual(self.waybills('?hide_delivered=1&hide_returned=1'), {'303400000001'})

    def test_left_hub_filter_still_shows_returned(self):
        self.assertEqual(self.waybills('?hide_returned=1&category=left_hub'), set())
        self.assertEqual(self.waybills('?category=left_hub'), {'303400000003'})