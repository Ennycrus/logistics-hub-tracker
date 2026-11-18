"""
Tests for the date checks on a status change:
  - the date cannot be before the shipment arrived
  - a date whose daily report is already finalized needs a confirmation
And for the shipment id in the import preview (used by the "Update" button there).

Run with:  python manage.py test shipments.test_date_checks
"""

import datetime

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import StatusOption
from reports.services.report_service import finalize, get_or_create_draft, save_draft, start_correction

from .models import TYPE_BASE
from .services.excel_reader import preview_scan_file
from .services.status_service import change_status, create_shipment
from .test_excel_reader import make_xlsx

MON = datetime.date(2026, 10, 26)
TUE = datetime.date(2026, 10, 27)


class DateCheckTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))
        self.delivered = StatusOption.objects.get(name='Delivered Successfully')
        self.temu = create_shipment('303400000001', first_seen_date=TUE)

    def post(self, shipment, **extra):
        body = {'status': self.delivered.pk, 'delivered_by': 'rider', **extra}
        return self.client.post(f'/api/shipments/{shipment.pk}/status/', body, format='json')

    # --- Before the shipment arrived -------------------------------------------

    def test_date_before_arrival_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            change_status(self.temu, self.delivered, effective_date=MON, delivered_by='rider')
        self.assertIn('only arrived on 27 Oct 2026', str(caught.exception))

    def test_date_before_arrival_is_refused_by_the_api(self):
        response = self.post(self.temu, effective_date=MON.isoformat())
        self.assertEqual(response.status_code, 400)
        self.assertIn('effective_date', response.json()['details'])

    def test_arrival_day_itself_is_fine(self):
        self.assertTrue(change_status(self.temu, self.delivered, effective_date=TUE, delivered_by='rider'))

    # --- Finalized day ---------------------------------------------------------

    def finalize_tuesday(self):
        finalize(save_draft(get_or_create_draft(TUE), vans=1, bikes=1, third_party=0), accept_warnings=True)

    def test_finalized_day_needs_confirmation(self):
        self.finalize_tuesday()
        response = self.post(self.temu, effective_date=TUE.isoformat())
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body['details']['code'], 'finalized_day')
        self.assertIn('TEMU report for Tue 27 Oct is already finalized', body['error'])
        self.temu.refresh_from_db()
        self.assertEqual(self.temu.status.category, 'unchecked')  # nothing saved

        confirmed = self.post(self.temu, effective_date=TUE.isoformat(), allow_finalized_day=True)
        self.assertEqual(confirmed.status_code, 200)
        self.assertTrue(confirmed.json()['changed'])

    def test_only_the_matching_type_counts(self):
        self.finalize_tuesday()  # TEMU only
        base = create_shipment('100000000001', first_seen_date=TUE, shipment_type=TYPE_BASE)
        self.assertEqual(self.post(base, effective_date=TUE.isoformat()).status_code, 200)

    def test_open_correction_needs_no_confirmation(self):
        self.finalize_tuesday()
        start_correction(TUE, 'Fixing deliveries')
        self.assertEqual(self.post(self.temu, effective_date=TUE.isoformat()).status_code, 200)

    def test_bulk_change_on_a_finalized_day_needs_confirmation(self):
        self.finalize_tuesday()
        other = create_shipment('303400000002', first_seen_date=TUE)
        body = {
            'status': self.delivered.pk, 'delivered_by': 'rider', 'effective_date': TUE.isoformat(),
            'shipment_ids': [self.temu.pk, other.pk],
        }
        response = self.client.post('/api/shipments/bulk-status/', body, format='json')
        self.assertEqual(response.json()['details']['code'], 'finalized_day')
        body['allow_finalized_day'] = True
        response = self.client.post('/api/shipments/bulk-status/', body, format='json')
        self.assertEqual(response.json()['changed'], 2)

    def test_adding_who_delivered_needs_no_confirmation(self):
        change_status(self.temu, self.delivered, effective_date=TUE)  # nobody recorded
        self.finalize_tuesday()
        response = self.post(self.temu, effective_date=TUE.isoformat(), delivered_by='captain')
        self.assertEqual(response.status_code, 200)

    def test_adding_who_with_an_older_remembered_date_is_fine(self):
        later = create_shipment('303400000003', first_seen_date=TUE + datetime.timedelta(days=1))
        change_status(later, self.delivered, effective_date=later.first_seen_date)
        # the page remembered Monday from earlier work; the delivery keeps its own date
        self.assertTrue(change_status(later, self.delivered, effective_date=MON, delivered_by='rider'))
        self.assertEqual(later.history.last().effective_date, later.first_seen_date)

    def test_day_not_finalized_needs_no_confirmation(self):
        self.assertEqual(self.post(self.temu, effective_date=TUE.isoformat()).status_code, 200)

    # --- Import preview --------------------------------------------------------

    def test_preview_gives_the_shipment_id_of_existing_waybills(self):
        rows = preview_scan_file(make_xlsx([['303400000001'], ['303400000099']]))['rows']
        self.assertEqual(rows[0]['shipment_id'], self.temu.pk)
        self.assertIsNone(rows[1]['shipment_id'])