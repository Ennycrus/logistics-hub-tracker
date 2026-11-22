"""
Tests for the TEMU return-waybill email list.

Run with:  python manage.py test shipments.test_returns_email
"""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import HubConfig, StatusOption

from .services.status_service import change_status, create_shipment

MON = datetime.date(2026, 11, 16)


class ReturnsEmailTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        self.returned = StatusOption.objects.create(
            name='Initiated Return', category=StatusOption.CATEGORY_LEFT_HUB,
        )

    def initiate_return(self, waybill, new_waybill, shipment_type='temu'):
        ship = create_shipment(waybill, first_seen_date=MON, shipment_type=shipment_type)
        change_status(ship, self.returned, effective_date=MON, note='3 attempts',
                      return_waybill=new_waybill)
        return ship

    def pending(self, query='?type=temu'):
        return self.client.get(f'/api/returns/pending/{query}').json()

    def test_only_returns_with_a_new_waybill_are_listed(self):
        self.initiate_return('303400000001', '1599000023')
        # Returned but no new waybill yet -> not listed.
        ship = create_shipment('303400000002', first_seen_date=MON)
        change_status(ship, self.returned, effective_date=MON, note='no waybill yet')
        data = self.pending()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['waybill_number'], '303400000001')
        self.assertEqual(data['results'][0]['return_waybill'], '1599000023')

    def test_recipients_and_subject_come_from_settings(self):
        config = HubConfig.get()
        config.return_email_to = 'a@x.com, b@x.com'
        config.return_email_subject = 'Temu RETURN WAYBILL DETAILS'
        config.save()
        self.initiate_return('303400000001', '1599000023')
        data = self.pending()
        self.assertEqual(data['email_to'], 'a@x.com, b@x.com')
        self.assertEqual(data['email_subject'], 'Temu RETURN WAYBILL DETAILS')

    def test_base_returns_are_separate(self):
        self.initiate_return('1000000001', '1599000099', shipment_type='base')
        self.assertEqual(self.pending('?type=temu')['count'], 0)
        self.assertEqual(self.pending('?type=base')['count'], 1)

    def test_mark_emailed_removes_them_from_the_list(self):
        ship = self.initiate_return('303400000001', '1599000023')
        resp = self.client.post('/api/returns/mark-emailed/', {'shipment_ids': [ship.pk]},
                                format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['marked'], 1)
        self.assertEqual(self.pending()['count'], 0)  # gone now
        ship.refresh_from_db()
        self.assertIsNotNone(ship.return_emailed_at)

    def test_return_waybill_is_saved_through_the_status_endpoint(self):
        ship = create_shipment('303400000001', first_seen_date=MON)
        resp = self.client.post(f'/api/shipments/{ship.pk}/status/', {
            'status': self.returned.pk, 'effective_date': '2026-11-17',
            'note': 'sent back', 'return_waybill': '1599000050',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['shipment']['return_waybill'], '1599000050')

    def test_bad_type_is_refused(self):
        self.assertEqual(self.client.get('/api/returns/pending/?type=boxes').status_code, 400)