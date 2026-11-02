"""
Tests for the Pending page filter: ?category=pending shows only shipments
still at the hub (not yet checked, outstanding or returned).

Run with:  python manage.py test reports
"""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import FailureReason, StatusOption
from shipments.services.status_service import change_status, create_shipment

MON = datetime.date(2026, 10, 26)
URL = f'/api/reports/{MON}/shipments/?kind=inbound'


class PendingFilterTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))

        status = {s.category: s for s in StatusOption.objects.all()}
        unavailable = FailureReason.objects.get(name='Customer unavailable')

        create_shipment('3034000001', first_seen_date=MON)  # not yet checked
        change_status(create_shipment('3034000002', first_seen_date=MON),
                      StatusOption.objects.get(name='Delivery Unsuccessful'),
                      failure_reason=unavailable, effective_date=MON)  # outstanding
        change_status(create_shipment('3034000003', first_seen_date=MON),
                      status['returned'], effective_date=MON)
        change_status(create_shipment('3034000004', first_seen_date=MON),
                      status['delivered'], effective_date=MON)
        change_status(create_shipment('3034000005', first_seen_date=MON),
                      status['left_hub'], effective_date=MON)  # rerouted

    def waybills(self, url):
        return sorted(r['shipment']['waybill_number'] for r in self.client.get(url).json()['results'])

    def test_pending_shows_only_shipments_still_at_the_hub(self):
        self.assertEqual(self.waybills(URL + '&category=pending'),
                         ['3034000001', '3034000002', '3034000003'])

    def test_no_filter_still_shows_everything(self):
        self.assertEqual(len(self.waybills(URL)), 5)

    def test_single_category_still_works(self):
        self.assertEqual(self.waybills(URL + '&category=delivered'), ['3034000004'])
