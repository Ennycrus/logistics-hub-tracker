"""
Tests for the trends endpoint (reports/trends/).

Run with:  python manage.py test reports.test_trends
"""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import FailureReason, StatusOption
from shipments.services.status_service import change_status, create_shipment


class TrendsTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        # Use the statuses and reasons seeded by migration 0002.
        self.delivered = StatusOption.objects.get(category=StatusOption.CATEGORY_DELIVERED)
        self.failed = StatusOption.objects.get(name='Delivery Unsuccessful')
        self.unavailable = FailureReason.objects.get(name='Customer unavailable')
        self.wrong_addr = FailureReason.objects.get(name='Incorrect or incomplete address')

        self.today = timezone.localdate()
        self.monday = self.today - datetime.timedelta(days=self.today.weekday())

    def trends(self, query='?type=temu'):
        return self.client.get(f'/api/reports/trends/{query}').json()

    def test_this_week_counts_deliveries_and_failures(self):
        for wb in ('303400000001', '303400000002'):
            s = create_shipment(wb, first_seen_date=self.monday)
            change_status(s, self.delivered, effective_date=self.monday)
        s = create_shipment('303400000003', first_seen_date=self.monday)
        change_status(s, self.failed, failure_reason=self.unavailable, effective_date=self.monday)
        change_status(s, self.failed, failure_reason=self.unavailable,
                      effective_date=self.monday + datetime.timedelta(days=1))

        data = self.trends('?type=temu&weeks=4')
        this_week = data['weeks'][-1]  # newest is last
        self.assertEqual(this_week['delivered'], 2)
        self.assertEqual(this_week['unsuccessful'], 2)  # two attempts, same shipment
        self.assertEqual(len(data['weeks']), 4)

    def test_top_reasons_are_ranked(self):
        a = create_shipment('303400000010', first_seen_date=self.monday)
        change_status(a, self.failed, failure_reason=self.unavailable, effective_date=self.today)
        b = create_shipment('303400000011', first_seen_date=self.monday)
        change_status(b, self.failed, failure_reason=self.unavailable, effective_date=self.today)
        c = create_shipment('303400000012', first_seen_date=self.monday)
        change_status(c, self.failed, failure_reason=self.wrong_addr, effective_date=self.today)

        reasons = self.trends('?type=temu')['top_reasons']
        self.assertEqual(reasons['total'], 3)
        self.assertEqual(reasons['reasons'][0], {'name': 'Customer unavailable', 'count': 2})
        self.assertEqual(reasons['reasons'][1], {'name': 'Incorrect or incomplete address', 'count': 1})

    def test_base_and_temu_are_separate(self):
        s = create_shipment('1000000001', first_seen_date=self.monday, shipment_type='base')
        change_status(s, self.delivered, effective_date=self.monday)
        self.assertEqual(self.trends('?type=temu&weeks=1')['weeks'][-1]['delivered'], 0)
        self.assertEqual(self.trends('?type=base&weeks=1')['weeks'][-1]['delivered'], 1)

    def test_bad_type_is_refused(self):
        self.assertEqual(self.client.get('/api/reports/trends/?type=boxes').status_code, 400)