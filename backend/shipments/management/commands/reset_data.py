"""
Delete all shipment and report data, to start fresh with real data.

    python manage.py reset_data          -> shows what will be deleted, asks you to type DELETE
    python manage.py reset_data --yes    -> no question (used by the tests)

DELETED:  shipments, their status history, imports, reporting days and reports
          (Base and TEMU).
KEPT:     your login, hub name, statuses and failure reasons (Settings).

A backup is ALWAYS made first (see backup_db), so this can be undone by
restoring that backup.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from reports.models import DailyReport, DailyShipmentRecord, ReportingDay
from shipments.models import ImportBatch, ImportRow, Shipment, StatusHistory

# Deleted in this order: things that point at others go first.
TABLES = [
    ('Report shipment records', DailyShipmentRecord),
    ('Reports (all versions)', DailyReport),
    ('Reporting days', ReportingDay),
    ('Import rows', ImportRow),
    ('Imports', ImportBatch),
    ('Status history rows', StatusHistory),
    ('Shipments', Shipment),
]


class Command(BaseCommand):
    help = 'Delete all shipments, imports and reports (keeps settings and users). Backs up first.'

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='Do not ask for confirmation.')
        parser.add_argument('--backup-dir', default=None, help='Folder for the safety backup.')

    def handle(self, *args, **options):
        counts = [(label, model.objects.count()) for label, model in TABLES]
        if not any(n for _, n in counts):
            self.stdout.write('Nothing to delete: there are no shipments, imports or reports.')
            return

        self.stdout.write('This will permanently delete:')
        for label, n in counts:
            self.stdout.write(f'  {label:<26} {n}')
        self.stdout.write('Kept: your login, hub name, statuses and failure reasons.')

        if not options['yes']:
            answer = input('Type DELETE to continue, anything else to cancel: ')
            if answer.strip() != 'DELETE':
                raise CommandError('Cancelled. Nothing was deleted.')

        backup_args = ['--dir', options['backup_dir']] if options['backup_dir'] else []
        call_command('backup_db', *backup_args, stdout=self.stdout)

        with transaction.atomic():
            # A correction points at the version it corrects, so remove those links first.
            DailyReport.objects.update(corrects=None)
            for _, model in TABLES:
                model.objects.all().delete()

        self.stdout.write(self.style.SUCCESS('Done. All shipment and report data was deleted.'))