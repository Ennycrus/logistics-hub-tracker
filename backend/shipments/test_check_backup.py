"""
Tests for the check_backup command.

Run with:  python manage.py test shipments.test_check_backup
"""

import datetime
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase

from .services.status_service import create_shipment


class CheckBackupTests(TransactionTestCase):
    serialized_rollback = True  # put the starting statuses and reasons back afterwards

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        create_shipment('303400000001', first_seen_date=datetime.date(2026, 11, 16))
        create_shipment('1000000001', first_seen_date=datetime.date(2026, 11, 16), shipment_type='base')

    def check(self, *args):
        out = StringIO()
        call_command('check_backup', '--dir', str(self.folder), *args, stdout=out)
        return out.getvalue()

    def backup(self):
        call_command('backup_db', '--dir', str(self.folder), '--copy-dir', '', stdout=StringIO())

    def test_newest_backup_is_healthy_and_matches(self):
        self.backup()
        output = self.check()
        self.assertIn('File is healthy.', output)
        self.assertIn('Same database structure as the app.', output)
        self.assertIn('This backup can be restored.', output)
        self.assertNotIn('differs', output)
        self.assertRegex(output, r'TEMU shipments\s+1\s+1')

    def test_changes_after_the_backup_show_as_differences(self):
        self.backup()
        create_shipment('303400000002', first_seen_date=datetime.date(2026, 11, 17))
        output = self.check()
        self.assertRegex(output, r'TEMU shipments\s+1\s+2\s+<- differs')
        self.assertIn('Some counts differ', output)

    def test_a_given_file_can_be_checked(self):
        self.backup()
        file = next(self.folder.glob('hub_*.sqlite3'))
        self.assertIn('This backup can be restored.', self.check(str(file)))

    def test_no_backups(self):
        with self.assertRaisesMessage(CommandError, 'No backups found'):
            self.check()

    def test_damaged_file_is_reported(self):
        bad = self.folder / 'hub_2026-11-20_000000.sqlite3'
        bad.write_bytes(b'this is not a database' * 100)
        with self.assertRaisesMessage(CommandError, 'damaged'):
            self.check()

    def test_the_backup_is_not_changed(self):
        self.backup()
        file = next(self.folder.glob('hub_*.sqlite3'))
        before = file.read_bytes()
        self.check()
        self.assertEqual(file.read_bytes(), before)
        

    def test_backup_is_one_file_that_stays_one_file(self):
        # The app's database uses WAL mode (extra -wal/-shm files while it runs).
        # A backup must be a single normal file, and checking it must not add any.
        self.backup()
        self.check()
        self.assertEqual([f.name for f in self.folder.iterdir()], [next(self.folder.glob('hub_*.sqlite3')).name])