"""
Tests for the Saturday hub report, the daily fuel and incidents log,
and recording who delivered a shipment.

Run with:  python manage.py test reports.test_weekly_hub
"""

import datetime
from io import BytesIO

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from openpyxl import load_workbook
from rest_framework.test import APIClient

from core.models import HubConfig, StatusOption
from shipments.models import TYPE_BASE
from shipments.services.status_service import bulk_change_status, change_status, create_shipment

from .services.report_service import finalize, get_or_create_draft, save_draft
from .services.weekly_hub import weekly_hub_report

MON = datetime.date(2026, 11, 9)
TUE = datetime.date(2026, 11, 10)
WED = datetime.date(2026, 11, 11)
SAT = datetime.date(2026, 11, 14)
LAST_SAT = datetime.date(2026, 11, 7)
URL = '/api/reports/weekly-hub/'
DAILY = '/api/reports/daily-log/'


class WeeklyHubTests(TestCase):

    def setUp(self):
        s = StatusOption.objects.get
        self.delivered = s(name='Delivered Successfully')
        self.pending = s(name='Pending Delivery')
        self.returned = s(name='Returned to Hub')
        self.rerouted = s(name='Rerouted to Another Hub')
        hub = HubConfig.get()
        hub.hub_name = 'Example Hub'
        hub.save()

        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user('tester'))

    def temu(self, n):
        return create_shipment(f'3034{n:06d}', first_seen_date=LAST_SAT)

    def base(self, n):
        return create_shipment(f'1{n:09d}', first_seen_date=LAST_SAT, shipment_type=TYPE_BASE)

    def deliver(self, shipment, by, date=WED):
        change_status(shipment, self.delivered, effective_date=date, delivered_by=by)

    # --- Who delivered ------------------------------------------------------

    def test_delivered_by_is_saved_on_shipment_and_history(self):
        a = self.temu(1)
        self.deliver(a, 'captain')
        a.refresh_from_db()
        self.assertEqual(a.delivered_by, 'captain')
        self.assertEqual(a.history.last().delivered_by, 'captain')

    def test_delivered_by_is_cleared_for_other_statuses(self):
        a = self.temu(1)
        change_status(a, self.pending, delivered_by='rider')
        a.refresh_from_db()
        self.assertEqual(a.delivered_by, '')

    def test_unknown_delivered_by_is_refused(self):
        with self.assertRaises(ValidationError):
            change_status(self.temu(1), self.delivered, delivered_by='drone')

    def test_changing_only_who_delivered_is_recorded(self):
        a = self.temu(1)
        self.deliver(a, 'rider')
        self.assertTrue(change_status(a, self.delivered, effective_date=WED, delivered_by='3pl',
                                      note='Wrong person'))
        a.refresh_from_db()
        self.assertEqual(a.delivered_by, '3pl')

    def test_bulk_delivered_by(self):
        a, b = self.temu(1), self.temu(2)
        bulk_change_status([a.pk, b.pk], self.delivered, effective_date=WED, delivered_by='3pl')
        self.assertEqual(weekly_hub_report(SAT)['figures']['delivered']['third_party'], 2)

    def test_api_status_change_accepts_delivered_by(self):
        a = self.temu(1)
        response = self.client.post(f'/api/shipments/{a.pk}/status/',
                                    {'status': self.delivered.pk, 'delivered_by': 'rider'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['shipment']['delivered_by'], 'rider')

    def test_api_refuses_unknown_delivered_by(self):
        a = self.temu(1)
        response = self.client.post(f'/api/shipments/{a.pk}/status/',
                                    {'status': self.delivered.pk, 'delivered_by': 'drone'}, format='json')
        self.assertEqual(response.status_code, 400)

    # --- Figures ------------------------------------------------------------

    def test_pending_per_type_and_not_in_hub(self):
        t1, t2, t3 = self.temu(1), self.temu(2), self.temu(3)  # all Not Yet Checked
        b1, b2 = self.base(1), self.base(2)
        change_status(t2, self.returned)
        change_status(t3, self.rerouted)        # left the hub: not pending
        self.deliver(b2, 'rider')               # delivered: not pending
        f = weekly_hub_report(SAT)['figures']
        self.assertEqual(f['temu_pending'], 2)  # t1 unchecked + t2 returned
        self.assertEqual(f['base_pending'], 1)  # b1
        self.assertEqual(f['not_in_hub'], 2)    # t1 and b1 still unchecked

    def test_delivered_split_and_only_this_week(self):
        shipments = [self.temu(n) for n in range(1, 7)]
        self.deliver(shipments[0], 'rider', MON)
        self.deliver(shipments[1], 'rider', SAT)
        self.deliver(shipments[2], 'captain')
        self.deliver(shipments[3], '3pl')
        self.deliver(shipments[4], 'rider', LAST_SAT)  # last week: not counted
        self.deliver(shipments[5], '')                 # nobody chosen
        d = weekly_hub_report(SAT)['figures']['delivered']
        self.assertEqual(d, {'riders': 2, 'captains': 1, 'third_party': 1,
                             'not_recorded': 1, 'total': 5})

    def test_delivered_then_undone_is_not_counted(self):
        a = self.temu(1)
        self.deliver(a, 'rider')
        change_status(a, self.pending, effective_date=WED, note='Marked by mistake')
        self.assertEqual(weekly_hub_report(SAT)['figures']['delivered']['total'], 0)

    def test_text_is_ready_to_paste(self):
        self.deliver(self.temu(1), 'rider')
        self.temu(2)
        self.log(MON, riders='8', captains='4.5')
        self.log(WED, riders='12', incidents='Van broke down\non Wednesday')
        self.client.post(f'{URL}?date={SAT}', {'extra_notes': 'Need one more rider'}, format='json')
        text = weekly_hub_report(SAT)['text']
        self.assertIn('Weekly Report - Example Hub', text)
        self.assertIn('Week: Mon 09 Nov - Sat 14 Nov 2026', text)
        self.assertIn('1. TEMU shipments pending in hub: 1', text)
        self.assertIn('2. Base shipments pending in hub: 0', text)
        self.assertIn('3. Shipments delivered: 1 (Riders 1, Captains 0, 3PLs 0)', text)
        self.assertIn('4. Shipments not in hub (awaiting update): 1 (already included in 1 and 2)', text)
        self.assertIn('5. Fuel used: Riders 20 litres, Captains 4.5 litres (entered for 2 of 6 days)', text)
        self.assertIn('6. Incidents/Escalations/Challenges/Difficulties:\n'
                      '   - Wed 11 Nov: Van broke down on Wednesday\n'
                      '   - Need one more rider', text)

    def test_nothing_entered_says_not_entered_and_none(self):
        text = weekly_hub_report(SAT)['text']
        self.assertIn('Riders not entered, Captains not entered', text)
        self.assertIn('Difficulties: None', text)

    # --- Daily log ----------------------------------------------------------

    def log(self, date, riders=None, captains=None, incidents=''):
        response = self.client.post(f'{DAILY}?date={date}', {
            'fuel_riders_litres': riders, 'fuel_captains_litres': captains, 'incidents': incidents,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_daily_log_save_and_read(self):
        self.assertIsNone(self.client.get(f'{DAILY}?date={WED}').json()['fuel_riders_litres'])
        self.log(WED, riders='7.50', incidents='  Late van  ')
        body = self.client.get(f'{DAILY}?date={WED}').json()
        self.assertEqual(body['fuel_riders_litres'], 7.5)
        self.assertIsNone(body['fuel_captains_litres'])
        self.assertEqual(body['incidents'], 'Late van')

    def test_saving_a_day_again_replaces_it(self):
        self.log(WED, riders='5')
        self.log(WED, riders='6')
        self.assertEqual(weekly_hub_report(SAT)['figures']['fuel']['riders'], 6)

    def test_fuel_adds_up_only_this_week(self):
        self.log(LAST_SAT, riders='100')  # last week
        self.log(MON, riders='3', captains='0')
        self.log(SAT, riders='2.25')
        fuel = weekly_hub_report(SAT)['figures']['fuel']
        self.assertEqual((fuel['riders'], fuel['captains'], fuel['days_entered']), (5.25, 0, 2))

    def test_missing_fuel_days_are_listed(self):
        self.log(MON, riders='3')
        self.log(WED, captains='2', incidents='Rain')  # incidents alone do not count as fuel
        self.log(TUE, incidents='No fuel typed')
        fuel = weekly_hub_report(SAT)['figures']['fuel']
        self.assertEqual(fuel['days_so_far'], 6)
        self.assertEqual(fuel['missing_days'], ['2026-11-10', '2026-11-12', '2026-11-13', '2026-11-14'])
        self.assertIn('(entered for 2 of 6 days)', weekly_hub_report(SAT)['text'])

    def test_all_fuel_days_entered_has_no_note(self):
        for n in range(6):
            self.log(MON + datetime.timedelta(days=n), riders='1')
        text = weekly_hub_report(SAT)['text']
        self.assertIn('Riders 6 litres, Captains not entered\n', text)
        self.assertNotIn('entered for', text)

    def test_week_table_shows_every_day(self):
        self.log(WED, captains='4', incidents='Rain')
        days = weekly_hub_report(SAT)['days']
        self.assertEqual([d['weekday'] for d in days],
                         ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'])
        self.assertEqual(days[2]['fuel_captains_litres'], 4)
        self.assertEqual(days[2]['incidents'], 'Rain')

    def test_negative_fuel_is_refused(self):
        response = self.client.post(f'{DAILY}?date={SAT}', {'fuel_riders_litres': -1}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('fuel_riders_litres', response.json()['details'])

    def test_future_daily_log_is_refused(self):
        response = self.client.post(f'{DAILY}?date=2999-01-01', {'incidents': 'x'}, format='json')
        self.assertEqual(response.status_code, 400)

    # --- Saving -------------------------------------------------------------

    def test_save_freezes_everything(self):
        a = self.temu(1)
        self.log(MON, riders='10')
        response = self.client.post(f'{URL}?date={WED}', {}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['saved'])

        self.deliver(a, 'rider')       # after saving
        self.log(WED, riders='5')      # after saving
        body = self.client.get(f'{URL}?date={SAT}').json()
        self.assertEqual(body['figures']['temu_pending'], 1)          # frozen
        self.assertEqual(body['figures']['fuel']['riders'], 10)       # frozen
        self.assertEqual(body['live_figures']['temu_pending'], 0)     # what it is now
        self.assertEqual(body['live_figures']['fuel']['riders'], 15)

    def test_saving_again_keeps_every_version(self):
        self.temu(1)
        self.client.post(f'{URL}?date={MON}', {'extra_notes': 'First'}, format='json')
        self.temu(2)
        body = self.client.post(f'{URL}?date={SAT}', {'extra_notes': 'Second'}, format='json').json()
        self.assertEqual((body['version'], body['versions']), (2, 2))

        history = self.client.get(f'{URL}history/').json()
        self.assertEqual([(h['week_start'], h['version']) for h in history], [(str(MON), 2), (str(MON), 1)])

        latest = self.client.get(f'{URL}?date={SAT}').json()
        self.assertEqual((latest['extra_notes'], latest['figures']['temu_pending']), ('Second', 2))
        first = self.client.get(f'{URL}?date={SAT}&version=1').json()
        self.assertEqual((first['extra_notes'], first['figures']['temu_pending']), ('First', 1))

        response = self.client.get(f'{URL}download/?date={SAT}&version=1')
        self.assertIn('Weekly_Report_2026-11-09_v1.xlsx', response['Content-Disposition'])

    def test_unknown_version_is_refused(self):
        self.assertEqual(self.client.get(f'{URL}?date={SAT}&version=9').status_code, 400)
        self.assertEqual(self.client.get(f'{URL}?date={SAT}&version=abc').status_code, 400)

    # --- Check against the daily reports ------------------------------------

    def test_daily_reports_check_spots_a_difference(self):
        self.deliver(self.temu(1), 'rider')  # no daily report finalized this week
        check = weekly_hub_report(SAT)['figures']['daily_reports']
        self.assertEqual(check, {'delivered': 0, 'missing_reports': 12, 'matches': False})

    def test_daily_reports_check_matches_a_finalized_report(self):
        a = create_shipment('3034000001', first_seen_date=MON)
        self.deliver(a, 'rider', MON)
        finalize(save_draft(get_or_create_draft(MON), vans=1, bikes=1, third_party=0), accept_warnings=True)
        check = weekly_hub_report(SAT)['figures']['daily_reports']
        self.assertEqual((check['delivered'], check['matches'], check['missing_reports']), (1, True, 11))

    def test_daily_reports_check_matches_when_both_are_zero(self):
        self.assertTrue(weekly_hub_report(SAT)['figures']['daily_reports']['matches'])

    # --- Filling in who delivered later ----------------------------------------

    def test_who_delivered_can_be_added_later_without_a_note(self):
        a = self.temu(1)
        self.deliver(a, '', MON)
        self.assertTrue(change_status(a, self.delivered, delivered_by='captain'))  # no note, today's date
        a.refresh_from_db()
        self.assertEqual(a.delivered_by, 'captain')
        self.assertEqual(a.history.last().effective_date, MON)  # keeps the delivery date
        d = weekly_hub_report(SAT)['figures']['delivered']
        self.assertEqual((d['captains'], d['not_recorded']), (1, 0))

    def test_late_fill_in_keeps_delivery_in_its_own_week(self):
        a = self.temu(1)
        self.deliver(a, '', LAST_SAT)
        change_status(a, self.delivered, delivered_by='rider')
        self.assertEqual(weekly_hub_report(SAT)['figures']['delivered']['total'], 0)

    def test_changing_who_delivered_still_needs_a_note(self):
        a = self.temu(1)
        self.deliver(a, 'rider')
        with self.assertRaises(ValidationError):
            change_status(a, self.delivered, delivered_by='captain')

    def test_future_date_is_refused(self):
        response = self.client.get(f'{URL}?date=2999-01-01')
        self.assertEqual(response.status_code, 400)

    def test_login_required(self):
        self.assertIn(APIClient().get(URL).status_code, (401, 403))
        self.assertIn(APIClient().get(DAILY).status_code, (401, 403))

    # --- Excel --------------------------------------------------------------

    def test_excel_download(self):
        self.deliver(self.temu(1), 'captain')
        self.log(TUE, captains='5', incidents='Gate locked at estate')
        self.client.post(f'{URL}?date={SAT}', {}, format='json')
        response = self.client.get(f'{URL}download/?date={SAT}')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Example_Hub_Weekly_Report_2026-11-09.xlsx', response['Content-Disposition'])
        sheet = load_workbook(BytesIO(response.content)).active
        values = {sheet.cell(row=r, column=2).value: sheet.cell(row=r, column=3).value
                  for r in range(6, 20)}
        self.assertEqual(values['Shipments delivered - total'], 1)
        self.assertEqual(values['   by Captains'], 1)
        self.assertEqual(values['Fuel used by Captains (litres)'], 5)
        self.assertEqual(values['Incidents / Escalations / Challenges / Difficulties'],
                         'Tue 10 Nov: Gate locked at estate')