"""
Show the calculated figures for a reporting day.

Usage:
    python manage.py day_summary --date 2026-10-28

The day's shipment list is refreshed first (same as open_day).
Nothing in the figures is saved yet.
"""

import datetime

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from reports.models import ReportingDay
from reports.services.calculations import calculate_day
from reports.services.day_service import open_or_refresh_day


class Command(BaseCommand):
    help = 'Show the calculated daily report figures.'

    def add_arguments(self, parser):
        parser.add_argument('--date', required=True, help='Format YYYY-MM-DD')

    def handle(self, *args, **options):
        try:
            date = datetime.date.fromisoformat(options['date'])
        except ValueError:
            raise CommandError('Date must look like 2026-10-28.')

        day = ReportingDay.objects.filter(date=date).first()
        if day is None or day.is_open:
            try:
                day, _ = open_or_refresh_day(date)
            except ValidationError as error:
                raise CommandError(error.messages[0])

        result = calculate_day(day)
        f = result['figures']

        self.stdout.write(self.style.SUCCESS(f"{result['hub_name']} - {result['date']}"))
        self.stdout.write(f"  Inbound:          {f['inbound']}")
        self.stdout.write(f"  Old Pending:      {f['old_pending']}")
        self.stdout.write(f"  Total Available:  {f['total_available']}")
        self.stdout.write(f"  Delivered:        {f['delivered']}")
        self.stdout.write(f"  Current Day:      {f['current_day']}")
        self.stdout.write(f"  Return:           {f['return']}")
        self.stdout.write(f"  (Rerouted:        {f['rerouted']})")
        self.stdout.write(f"  (Unsuccessful:    {f['unsuccessful']})")
        self.stdout.write(f"  (Not yet checked: {f['unchecked']})")
        self.stdout.write(f"  Reasons:          {result['reasons_text'] or '-'}")

        r = result['reconciliation']
        check = 'balanced' if r['balanced'] else 'DOES NOT BALANCE'
        self.stdout.write(
            f"\n  Check: {r['delivered']} + {r['current_day']} + {r['rerouted']} = "
            f"{r['accounted_for']} vs Total Available {r['total_available']} -> {check}"
        )

        if result['warnings']:
            self.stdout.write(self.style.WARNING('\nWarnings:'))
            for warning in result['warnings']:
                self.stdout.write(self.style.WARNING(f"  - {warning['message']}"))