"""
Open (or refresh) a reporting day and list its Inbound and Old Pending counts.

Usage:
    python manage.py open_day --date 2026-10-28

Run it after importing that day's scanner file. Running it again is safe.
"""

import datetime

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from reports.services.day_service import open_or_refresh_day


class Command(BaseCommand):
    help = 'Open or refresh a reporting day.'

    def add_arguments(self, parser):
        parser.add_argument('--date', required=True, help='Format YYYY-MM-DD')

    def handle(self, *args, **options):
        try:
            date = datetime.date.fromisoformat(options['date'])
        except ValueError:
            raise CommandError('Date must look like 2026-10-28.')

        try:
            day, summary = open_or_refresh_day(date)
        except ValidationError as error:
            raise CommandError(error.messages[0])

        self.stdout.write(self.style.SUCCESS(f'Reporting day {day.date} is {day.get_state_display()}.'))
        self.stdout.write(f"  Inbound:          {summary['inbound']}")
        self.stdout.write(f"  Old Pending:      {summary['old_pending']}")
        self.stdout.write(f"  Total Available:  {summary['inbound'] + summary['old_pending']}")
        self.stdout.write(
            f"  (this run: {summary['added']} added, {summary['changed']} changed, "
            f"{summary['removed']} removed)"
        )