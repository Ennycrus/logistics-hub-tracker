"""
Restore the database from a backup, safely.

    python manage.py restore_db                 -> restore the NEWEST backup
    python manage.py restore_db "C:\\...\\hub_2026-11-21_083000.sqlite3"
    python manage.py restore_db --dir "G:\\My Drive\\Hub Tracker backups"
    python manage.py restore_db --yes           -> don't ask for confirmation

Before anything is overwritten, the CURRENT database is saved to
backups/pre_restore_<date>.sqlite3, so a restore can itself be undone.

IMPORTANT: stop Django first (Ctrl+C in the backend window). The database
file cannot be replaced while the server is using it; if it is still running,
this command stops safely and asks you to close it and try again, without
changing your data.
"""

import os
import shutil
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from .backup_db import PREFIX


def newest_backup(folder):
    """The most recent hub_*.sqlite3 in the folder, or None."""
    backups = sorted(folder.glob(f'{PREFIX}*.sqlite3'))
    return backups[-1] if backups else None


def health_problem(path):
    """Return a reason the file can't be used as a database, or '' if it's fine."""
    try:
        con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    except sqlite3.Error:
        return 'the file could not be opened as a database'
    try:
        if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            return 'the integrity check failed (the file looks damaged)'
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'django_migrations' not in tables:
            return 'it does not look like a Hub Tracker database (no migrations table)'
    except sqlite3.Error:
        return 'the file is not a valid SQLite database'
    finally:
        con.close()
    return ''


class Command(BaseCommand):
    help = 'Restore the database from a backup (saves the current one first).'

    def add_arguments(self, parser):
        parser.add_argument('file', nargs='?', help='Backup file to restore (default: the newest backup).')
        parser.add_argument('--dir', default=None, help='Backups folder (default: backups next to manage.py).')
        parser.add_argument('--yes', action='store_true', help='Do not ask for confirmation.')

    def handle(self, *args, **options):
        if connection.vendor != 'sqlite':
            raise CommandError('restore_db only works with the SQLite database.')

        folder = Path(options['dir']) if options['dir'] else Path(settings.BASE_DIR) / 'backups'
        if options['file']:
            source = Path(options['file'])
        else:
            source = newest_backup(folder)
            if source is None:
                raise CommandError(f'No backups found in {folder}.')
        if not source.exists():
            raise CommandError(f'Backup not found: {source}')

        problem = health_problem(source)
        if problem:
            raise CommandError(f'Will not restore {source.name}: {problem}.')

        live = Path(settings.BASE_DIR) / 'db.sqlite3'

        self.stdout.write(f'About to restore: {source}')
        self.stdout.write(f'Into: {live}')
        self.stdout.write(self.style.WARNING(
            'This replaces your current data. The current database will be saved first.'
        ))
        if not options['yes']:
            if input('Type "yes" to continue: ').strip().lower() != 'yes':
                self.stdout.write('Cancelled. Nothing was changed.')
                return

        # 1. Save the current database first, so this restore can be undone.
        folder.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime('%Y-%m-%d_%H%M%S')
        safety = folder / f'pre_restore_{stamp}.sqlite3'
        if live.exists():
            try:
                self._snapshot(live, safety)
            except sqlite3.Error as error:
                raise CommandError(f'Could not save the current database ({error}). Nothing was changed.')
            self.stdout.write(self.style.SUCCESS(f'Current database saved: {safety}'))
        else:
            self.stdout.write('No current database found; a fresh one will be created from the backup.')

        # Let go of Django's own connection before touching the files.
        connection.close()

        # 2. Copy the backup in beside the live file, so the swap itself is atomic.
        incoming = live.with_name('db.sqlite3.incoming')
        try:
            shutil.copy2(source, incoming)
        except OSError as error:
            raise CommandError(f'Could not prepare the restore ({error}). Nothing was changed.')

        # 3. Swap it in. The old WAL side-files must go first, or SQLite would
        #    replay them over the restored database.
        try:
            for extra in ('db.sqlite3-wal', 'db.sqlite3-shm'):
                side = live.with_name(extra)
                if side.exists():
                    side.unlink()
            os.replace(incoming, live)  # atomic within the same folder
        except OSError as error:
            if incoming.exists():
                incoming.unlink()
            raise CommandError(
                f'Could not replace the database ({error}). '
                'Is Django still running? Stop it (Ctrl+C in the backend window) and run this again. '
                'Your data was not changed.'
            )

        self.stdout.write(self.style.SUCCESS(
            f'Restored {source.name}. Start Django again to use it.'
        ))

    def _snapshot(self, live, target):
        """Copy the live database to a single-file snapshot using SQLite's backup API."""
        src = sqlite3.connect(live)          # read-write: handles WAL correctly
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
            dst.execute('PRAGMA journal_mode=DELETE')  # single file, no side-files
        finally:
            dst.close()
            src.close()