"""
Tests for the reports API.

Run with:  python manage.py test reports
"""

import datetime
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIClient

from core.models import FailureReason, StatusOption
from shipments.services.status_service import change_status, create_shipment

MON = datetime.date(2026, 10, 26)
URL = f'/api/reports/{MON}/'


class ReportApiTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))

        delivered = StatusOption.objects.get(name='Delivered Successfully')
        unsuccessful = StatusOption.objects.get(name='Delivery Unsuccessful')
        unavailable = FailureReason.objects.get(name='Customer unavailable')
        change_status(create_shipment('D1', first_seen_date=MON), delivered, effective_date=MON)
        change_status(create_shipment('U1', first_seen_date=MON), unsuccessful,
                      failure_reason=unavailable, effective_date=MON)

    def fill_transport(self):
        return self.client.patch(URL, {'vans': 2, 'bikes': 6, 'third_party': 3}, format='json')

    # --- Draft --------------------------------------------------------------

    def test_get_opens_a_draft_with_preview(self):
        body = self.client.get(URL).json()
        self.assertEqual(body['state'], 'draft')
        self.assertEqual(body['preview']['figures']['total_available'], 2)
        self.assertEqual(body['preview']['figures']['delivered'], 1)
        self.assertEqual(len(body['preview']['problems']), 3)  # transport missing

    def test_patch_saves_transport(self):
        body = self.fill_transport().json()
        self.assertEqual(body['report']['vans'], 2)
        self.assertEqual(body['preview']['problems'], [])

    def test_patch_keeps_fields_you_did_not_send(self):
        self.fill_transport()
        body = self.client.patch(URL, {'notes': 'Rain'}, format='json').json()
        self.assertEqual(body['report']['vans'], 2)
        self.assertEqual(body['report']['notes'], 'Rain')

    def test_adjustment_without_note_is_refused(self):
        response = self.client.patch(
            URL, {'adjust': {'delivered': {'value': 5, 'note': ''}}}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_adjustment_is_applied(self):
        body = self.client.patch(
            URL, {'adjust': {'delivered': {'value': 5, 'note': 'Gate count'}}}, format='json',
        ).json()
        self.assertEqual(body['preview']['figures']['delivered'], 5)
        self.assertEqual(body['preview']['calculated']['delivered'], 1)

    def test_negative_transport_is_refused(self):
        response = self.client.patch(URL, {'vans': -1}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_bad_and_future_dates_are_refused(self):
        self.assertEqual(self.client.get('/api/reports/29-10-2026/').status_code, 400)
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        self.assertEqual(self.client.get(f'/api/reports/{tomorrow}/').status_code, 400)

    # --- Finalize -----------------------------------------------------------

    def test_finalize_needs_transport(self):
        response = self.client.post(f'{URL}finalize/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('No of Vans', response.json()['error'])

    def test_finalize_and_read_back(self):
        self.fill_transport()
        response = self.client.post(f'{URL}finalize/', {}, format='json')
        self.assertEqual(response.status_code, 200)

        body = self.client.get(URL).json()
        self.assertEqual(body['state'], 'finalized')
        self.assertEqual(body['report']['figures']['current_day'], 1)
        self.assertEqual(body['report']['reasons_text'], 'Customer unavailable - 1')

    def test_warnings_must_be_accepted(self):
        create_shipment('NEW', first_seen_date=MON)  # unchecked -> warning
        self.fill_transport()

        refused = self.client.post(f'{URL}finalize/', {}, format='json')
        self.assertEqual(refused.status_code, 400)
        accepted = self.client.post(f'{URL}finalize/', {'accept_warnings': True}, format='json')
        self.assertEqual(accepted.status_code, 200)

    def test_finalized_report_cannot_be_patched(self):
        self.fill_transport()
        self.client.post(f'{URL}finalize/', {}, format='json')
        response = self.client.patch(URL, {'vans': 9}, format='json')
        self.assertEqual(response.status_code, 400)

    # --- Corrections --------------------------------------------------------

    def test_correction_flow(self):
        self.fill_transport()
        self.client.post(f'{URL}finalize/', {}, format='json')

        started = self.client.post(f'{URL}correct/', {'reason': 'Vans wrong'}, format='json')
        self.assertEqual(started.status_code, 201)
        self.assertEqual(started.json()['report']['version'], 2)

        self.client.patch(URL, {'vans': 4}, format='json')
        final = self.client.post(f'{URL}finalize/', {}, format='json').json()
        self.assertEqual(final['report']['vans'], 4)
        self.assertEqual(final['report']['corrects_version'], 1)

    def test_correction_needs_reason(self):
        self.fill_transport()
        self.client.post(f'{URL}finalize/', {}, format='json')
        response = self.client.post(f'{URL}correct/', {'reason': ''}, format='json')
        self.assertEqual(response.status_code, 400)

    # --- Download and history -----------------------------------------------

    def test_download_before_finalize_is_refused(self):
        response = self.client.get(f'{URL}download/')
        self.assertEqual(response.status_code, 400)

    def test_download_returns_excel(self):
        self.fill_transport()
        self.client.post(f'{URL}finalize/', {}, format='json')
        response = self.client.get(f'{URL}download/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertEqual(sheet['A5'].value, 'HUBS')

    def test_download_specific_version(self):
        self.fill_transport()
        self.client.post(f'{URL}finalize/', {}, format='json')
        self.client.post(f'{URL}correct/', {'reason': 'Fix'}, format='json')
        self.client.patch(URL, {'vans': 4}, format='json')
        self.client.post(f'{URL}finalize/', {}, format='json')

        v1 = self.client.get(f'{URL}download/?version=1')
        latest = self.client.get(f'{URL}download/')
        self.assertNotIn('_v2', v1['Content-Disposition'])
        self.assertIn('_v2', latest['Content-Disposition'])

    def test_history_lists_finalized_reports_only(self):
        self.client.get(URL)  # draft only
        self.assertEqual(self.client.get('/api/reports/').json()['count'], 0)

        self.fill_transport()
        self.client.post(f'{URL}finalize/', {}, format='json')
        history = self.client.get('/api/reports/').json()
        self.assertEqual(history['count'], 1)
        self.assertEqual(history['results'][0]['date'], str(MON))