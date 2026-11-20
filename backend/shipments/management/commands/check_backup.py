"""
Check that a backup can really be restored, WITHOUT touching your data.

    python manage.py check_backup                     -> checks the newest backup
    python manage.py check_backup "G:\\My Drive\\Hub Tracker backups\\hub_....sqlite3"

It opens the backup read-only and:
  1. Asks SQLite whether the file is healthy (not damaged or cut off).
  2. Checks it has the same database structure (migrations) as the app.
  3. Counts what is inside, next to the same counts in the app right now.

If the file is healthy and the counts look right, the backup can be restored
(the steps are at the top of backup_db.py). Counts can differ a little when
you worked in the app after the backup was made; that is normal.
"""

import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from reports.models import DailyHubLog, DailyReport, ReportingDay, WeeklyHubReport
from shipments.models import ImportBatch, Shipment, StatusHistory

from .backup_db import PREFIX


def checks():
    """(label, SQL) pairs. Run the same way on the backup and on the app's database."""
    shipment = Shipment._meta.db_table
    report = DailyReport._meta.db_table
    day = ReportingDay._meta.db_table
    return [
        ('TEMU shipments', f"SELECT COUNT(*) FROM {shipment} WHERE shipment_type = 'temu'"),
        ('Base shipments', f"SELECT COUNT(*) FROM {shipment} WHERE shipment_type = 'base'"),
        ('Status changes', f'SELECT COUNT(*) FROM {StatusHistory._meta.db_table}'),
        ('Imports', f'SELECT COUNT(*) FROM {ImportBatch._meta.db_table}'),
        ('Finalized daily reports', f'SELECT COUNT(*) FROM {report} WHERE is_finalized = 1'),
        ('Latest finalized day', (
            f'SELECT MAX(d.date) FROM {report} r JOIN {day} d ON d.id = r.day_id WHERE r.is_finalized = 1'
        )),
        ('Saturday reports', f'SELECT COUNT(*) FROM {WeeklyHubReport._meta.db_table}'),
        ('Fuel / incident days', f'SELECT COUNT(*) FROM {DailyHubLog._meta.db_table}'),
    ]


def run(cursor, sql):
    cursor.execute(sql)
    value = cursor.fetchone()[0]
    return '-' if value is None else str(value)


class Command(BaseCommand):
    help = 'Check that a backup is healthy and show what it contains (read-only).'

    def add_arguments(self, parser):
        parser.add_argument('file', nargs='?', help='Backup file to check (default: the newest backup).')
        parser.add_argument('--dir', default=None, help='Backups folder (default: backups next to manage.py).')

    def handle(self, *args, **options):
        if connection.vendor != 'sqlite':
            raise CommandError('check_backup only works with the SQLite database.')
        path = Path(options['file']) if options['file'] else self.newest(options['dir'])
        if not path.is_file():
            raise CommandError(f'No such file: {path}')

        self.stdout.write(f'Checking {path} ({path.stat().st_size / 1024:.0f} KB)')
        try:
            backup = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True)  # read-only
        except sqlite3.Error as error:
            raise CommandError(f'Could not open the backup: {error}')
        try:
            self.compare(backup.cursor())
        except sqlite3.DatabaseError as error:
            raise CommandError(f'This backup is damaged or is not a Hub Tracker database: {error}')
        finally:
            backup.close()

    def newest(self, folder):
        folder = Path(folder) if folder else Path(settings.BASE_DIR) / 'backups'
        backups = sorted(folder.glob(f'{PREFIX}*.sqlite3'))
        if not backups:
            raise CommandError(f'No backups found in {folder}. Run: python manage.py backup_db')
        return backups[-1]

    def compare(self, backup):
        # 1. Is the file healthy?
        result = run(backup, 'PRAGMA integrity_check')
        if result != 'ok':
            raise CommandError(f'The backup file is damaged: {result}')
        self.stdout.write(self.style.SUCCESS('File is healthy.'))

        with connection.cursor() as app:
            # 2. Same structure as the app?
            migrations = 'SELECT COUNT(*) FROM django_migrations'
            if run(backup, migrations) != run(app, migrations):
                self.stdout.write(self.style.WARNING(
                    'The backup was made with an older or newer version of the app '
                    '(different migrations). After restoring it, run: python manage.py migrate'
                ))
            else:
                self.stdout.write(self.style.SUCCESS('Same database structure as the app.'))

            # 3. What is inside, next to the app now.
            rows = [(label, run(backup, sql), run(app, sql)) for label, sql in checks()]

        width = max(len(label) for label, _, _ in rows)
        self.stdout.write('')
        self.stdout.write(f'{"":{width}}   {"Backup":>10}   {"App now":>10}')
        for label, in_backup, now in rows:
            line = f'{label:{width}}   {in_backup:>10}   {now:>10}'
            self.stdout.write(line if in_backup == now else self.style.WARNING(f'{line}   <- differs'))
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('This backup can be restored.'))
        if any(in_backup != now for _, in_backup, now in rows):
            self.stdout.write(
                'Some counts differ: normal if you used the app after this backup was made.'
            )