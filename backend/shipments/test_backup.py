"""
Tests for the backup_db command.

Run with:  python manage.py test shipments
"""

import datetime
import sqlite3
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TransactionTestCase

from .services.status_service import create_shipment


class BackupCommandTests(TransactionTestCase):
    # TransactionTestCase: data is really saved (not held in an open
    # transaction), the same as when you run the command yourself.
    # serialized_rollback puts the starting statuses and reasons back afterwards.
    serialized_rollback = True

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())

    def backup(self, *args):
        out = StringIO()
        call_command('backup_db', '--dir', str(self.folder), *args, stdout=out)
        return out.getvalue()

    def test_backup_contains_the_data(self):
        create_shipment('303400000001', first_seen_date=datetime.date(2026, 10, 26))
        output = self.backup()

        files = list(self.folder.glob('hub_*.sqlite3'))
        self.assertEqual(len(files), 1)
        self.assertIn('Backup saved', output)

        copy = sqlite3.connect(files[0])
        waybills = [row[0] for row in copy.execute('SELECT waybill_number FROM shipments_shipment')]
        copy.close()
        self.assertEqual(waybills, ['303400000001'])

    def test_only_the_newest_copies_are_kept(self):
        times = ['2026-10-30_090000', '2026-10-30_100000', '2026-10-30_110000']
        for stamp in times:
            with mock.patch('django.utils.timezone.localtime') as fake:
                fake.return_value.strftime.return_value = stamp
                self.backup('--keep', '2')

        names = sorted(f.name for f in self.folder.glob('hub_*.sqlite3'))
        self.assertEqual(names, ['hub_2026-10-30_100000.sqlite3', 'hub_2026-10-30_110000.sqlite3'])