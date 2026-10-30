"""
Tests for shipment notes and the history shown in the website.

Run with:  python manage.py test shipments
"""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import StatusOption

from .models import StatusHistory
from .services.status_service import change_status, create_shipment

MON = datetime.date(2026, 10, 26)


class NotesApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        self.shipment = create_shipment('A1', first_seen_date=MON)
        self.url = f'/api/shipments/{self.shipment.pk}/notes/'

    def test_save_notes(self):
        response = self.client.patch(self.url, {'notes': '  Call before 5pm  '}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['notes'], 'Call before 5pm')  # spaces trimmed
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.notes, 'Call before 5pm')

    def test_notes_can_be_cleared(self):
        self.client.patch(self.url, {'notes': 'Something'}, format='json')
        self.client.patch(self.url, {'notes': ''}, format='json')
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.notes, '')

    def test_notes_do_not_change_status_or_history(self):
        history_before = StatusHistory.objects.count()
        self.client.patch(self.url, {'notes': 'Hello'}, format='json')
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.status.name, 'Not Yet Checked')
        self.assertEqual(StatusHistory.objects.count(), history_before)

    def test_notes_are_required_in_the_request(self):
        response = self.client.patch(self.url, {}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_very_long_notes_are_refused(self):
        response = self.client.patch(self.url, {'notes': 'x' * 1001}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_unknown_shipment_is_404(self):
        response = self.client.patch('/api/shipments/99999/notes/', {'notes': 'x'}, format='json')
        self.assertEqual(response.status_code, 404)

    def test_detail_shows_full_history_in_order(self):
        change_status(self.shipment, StatusOption.objects.get(name='Pending Delivery'), note='First try')
        change_status(self.shipment, StatusOption.objects.get(name='Delivered Successfully'))

        history = self.client.get(f'/api/shipments/{self.shipment.pk}/').json()['history']
        self.assertEqual(
            [h['new_status'] for h in history],
            ['Not Yet Checked', 'Pending Delivery', 'Delivered Successfully'],
        )
        self.assertEqual(history[1]['note'], 'First try')
        