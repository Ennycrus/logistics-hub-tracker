"""
Finalize a day's report: its figures are frozen and can never change.

Usage:
    python manage.py finalize_report --date 2026-10-28
    python manage.py finalize_report --date 2026-10-28 --accept-warnings
"""

import datetime

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from reports.management.commands.report_inputs import print_preview
from reports.services.report_service import finalize, get_or_create_draft


class Command(BaseCommand):
    help = "Finalize a day's report."

    def add_arguments(self, parser):
        parser.add_argument('--date', required=True, help='Format YYYY-MM-DD')
        parser.add_argument('--accept-warnings', action='store_true',
                            help='Finalize even though there are warnings')

    def handle(self, *args, **options):
        try:
            date = datetime.date.fromisoformat(options['date'])
        except ValueError:
            raise CommandError('Date must look like 2026-10-28.')

        try:
            draft = get_or_create_draft(date)
            print_preview(self, draft)
            report = finalize(draft, accept_warnings=options['accept_warnings'])
        except ValidationError as error:
            raise CommandError(' '.join(error.messages))

        self.stdout.write(self.style.SUCCESS(
            f'\nFinalized {report.day.date} (version {report.version}). These figures are now frozen.'
        ))