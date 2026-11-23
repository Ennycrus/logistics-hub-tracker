"""
Tests for the restore_db guards (health check and newest-backup lookup).

These use hand-made SQLite files and SimpleTestCase (no database transaction),
so they never touch the real db.sqlite3. The full file swap is exercised by hand.

Run with:  python manage.py test shipments.test_restore_db
"""

import pathlib
import sqlite3
import tempfile

from django.test import SimpleTestCase

from shipments.management.commands.backup_db import PREFIX
from shipments.management.commands.restore_db import health_problem, newest_backup


def make_hub_db(path):
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE django_migrations (id INTEGER PRIMARY KEY, app TEXT, name TEXT)')
    con.commit()
    con.close()


class RestoreDbHelpersTests(SimpleTestCase):

    def test_a_valid_hub_database_is_healthy(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / f'{PREFIX}2026-11-21_0800.sqlite3'
            make_hub_db(path)
            self.assertEqual(health_problem(path), '')  # '' = no problem

    def test_a_database_without_migrations_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 'other.sqlite3'
            con = sqlite3.connect(path)
            con.execute('CREATE TABLE something (a)')
            con.commit()
            con.close()
            self.assertIn('Hub Tracker', health_problem(path))

    def test_a_junk_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 'junk.sqlite3'
            path.write_text('this is not a database')
            self.assertIn('not a valid', health_problem(path))

    def test_newest_backup_picks_the_latest_and_handles_empty(self):
        with tempfile.TemporaryDirectory() as d:
            folder = pathlib.Path(d)
            self.assertIsNone(newest_backup(folder))
            older = folder / f'{PREFIX}2026-11-20_0800.sqlite3'
            newer = folder / f'{PREFIX}2026-11-21_0800.sqlite3'
            older.write_text('x')
            newer.write_text('x')
            self.assertEqual(newest_backup(folder), newer)