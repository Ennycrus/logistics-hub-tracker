"""
Start a correction for a finalized report. The original is kept unchanged.

Usage:
    python manage.py correct_report --date 2026-10-28 --reason "Vans figure was wrong"

Then use report_inputs to fix the figures and finalize_report to finalize
the corrected version.
"""

import datetime

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from reports.management.commands.report_inputs import print_preview
from reports.services.report_service import start_correction


class Command(BaseCommand):
    help = 'Start a correction (new version) of a finalized report.'

    def add_arguments(self, parser):
        parser.add_argument('--date', required=True, help='Format YYYY-MM-DD')
        parser.add_argument('--reason', required=True, help='Why the report needs correcting')

    def handle(self, *args, **options):
        try:
            date = datetime.date.fromisoformat(options['date'])
        except ValueError:
            raise CommandError('Date must look like 2026-10-28.')

        try:
            draft = start_correction(date, options['reason'])
        except ValidationError as error:
            raise CommandError(' '.join(error.messages))

        self.stdout.write(self.style.SUCCESS(
            f'Correction started: version {draft.version} (corrects version {draft.corrects.version}).'
        ))
        print_preview(self, draft)