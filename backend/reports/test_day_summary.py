"""
Smoke test for the day_summary CLI command.

It isn't part of the report flow, so the figure tests don't cover it - which is
how a figures rename once broke its reconciliation line unnoticed. This test
just runs the command end to end and checks it prints without crashing.

Run with:  python manage.py test reports.test_day_summary
"""

import datetime
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.models import StatusOption
from shipments.services.status_service import change_status, create_shipment

MON = datetime.date(2026, 10, 26)


class DaySummaryCommandTests(TestCase):

    def test_runs_and_prints_the_return_and_check_lines(self):
        rerouted = StatusOption.objects.get(name='Rerouted to Another Hub')
        delivered = StatusOption.objects.get(name='Delivered Successfully')
        change_status(create_shipment('303400000001', first_seen_date=MON), rerouted, effective_date=MON)
        change_status(create_shipment('303400000002', first_seen_date=MON), delivered, effective_date=MON)

        out = StringIO()
        call_command('day_summary', date=MON.isoformat(), stdout=out)
        text = out.getvalue()

        self.assertIn('Return:', text)
        self.assertIn('Check:', text)     # the reconciliation line renders (no KeyError)
        self.assertIn('balanced', text)   # 1 delivered + 0 current day + 1 return = 2 available

    def test_rejects_a_bad_date(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('day_summary', date='not-a-date', stdout=StringIO())