"""
Export a finalized report to an Excel file in the company's layout.

Usage:
    python manage.py export_report --date 2026-10-28
    python manage.py export_report --date 2026-10-28 --report-version 1
    python manage.py export_report --date 2026-10-28 --out "C:\\Users\\USER\\Desktop"

Without --report-version, the latest finalized version is exported.
Without --out, the file is saved in the current folder.
"""

import datetime
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from reports.models import DailyReport
from reports.services.excel_export import export_file_name, export_report_bytes
from reports.services.report_service import current_report


class Command(BaseCommand):
    help = 'Export a finalized daily report to Excel.'

    def add_arguments(self, parser):
        parser.add_argument('--date', required=True, help='Format YYYY-MM-DD')
        parser.add_argument('--report-version', type=int, help='Which version (default: latest finalized)')
        parser.add_argument('--out', default='.', help='Folder to save the file in')

    def handle(self, *args, **options):
        try:
            date = datetime.date.fromisoformat(options['date'])
        except ValueError:
            raise CommandError('Date must look like 2026-10-28.')

        if options['report_version']:
            report = DailyReport.objects.filter(
                day__date=date, version=options['report_version'], is_finalized=True,
            ).first()
        else:
            report = current_report(date)
        if report is None:
            raise CommandError(f'No finalized report found for {date}.')

        folder = Path(options['out'])
        if not folder.is_dir():
            raise CommandError(f'Folder not found: {folder}')

        try:
            data = export_report_bytes(report)
        except ValidationError as error:
            raise CommandError(' '.join(error.messages))

        path = folder / export_file_name(report)
        path.write_bytes(data)
        self.stdout.write(self.style.SUCCESS(f'Saved {path.resolve()}'))