"""
Import a gun-scanner Excel file for a reporting date (this SAVES to the database).

Usage:
    python manage.py import_scan scan.xlsx --date 2026-10-28
    python manage.py import_scan scan.xlsx --date 2026-10-28 --column 1

Run preview_scan first to check the file.
"""

import datetime
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from shipments.services.import_service import confirm_import


class Command(BaseCommand):
    help = 'Import a gun-scanner Excel file and create new shipments.'

    def add_arguments(self, parser):
        parser.add_argument('path', help='Path to the .xlsx file')
        parser.add_argument('--date', required=True,
                            help='Reporting date, format YYYY-MM-DD (e.g. 2026-10-28)')
        parser.add_argument('--column', type=int, default=None,
                            help='0-based column number to use (A=0, B=1, ...)')

    def handle(self, *args, **options):
        try:
            reporting_date = datetime.date.fromisoformat(options['date'])
        except ValueError:
            raise CommandError('Date must look like 2026-10-28.')

        path = Path(options['path'])
        try:
            with open(path, 'rb') as file:
                batch = confirm_import(
                    file,
                    reporting_date=reporting_date,
                    column_index=options['column'],
                    file_name=path.name,
                )
        except FileNotFoundError:
            raise CommandError('File not found. Check the path (use quotes if it has spaces).')
        except ValidationError as error:
            raise CommandError(error.messages[0])

        self.stdout.write(self.style.SUCCESS(
            f'Imported "{batch.file_name}" for {batch.reporting_date} (batch #{batch.pk}).'
        ))
        self.stdout.write(f'  Rows read:              {batch.total_rows}')
        self.stdout.write(f'  New shipments created:  {batch.new_count}')
        self.stdout.write(f'  Duplicates in file:     {batch.duplicate_in_file_count}')
        self.stdout.write(f'  Already at hub:         {batch.existing_outstanding_count}')
        self.stdout.write(f'  Closed, needs review:   {batch.existing_closed_count}')
        self.stdout.write(f'  Invalid:                {batch.invalid_count}')