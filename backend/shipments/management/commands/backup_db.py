"""
Make a safe copy of the database.

    python manage.py backup_db              -> backups/hub_2026-10-30_1315.sqlite3
    python manage.py backup_db --keep 60    -> keep the newest 60 copies (default 30)

Second copy off the laptop: set BACKUP_COPY_DIR in .env (e.g. your Google
Drive folder) and every backup is also copied there, with the same --keep.
If that folder can't be reached (Drive not running, flash drive out), the
normal backup is still made and a warning is printed.

The copy uses SQLite's own backup feature, so it is safe even while the
website is running. Old copies beyond --keep are deleted, newest kept.

To RESTORE a copy:
    1. Stop Django (Ctrl+C).
    2. Rename db.sqlite3 to db_broken.sqlite3 (keep it, just in case).
    3. Copy the backup file next to manage.py and rename it db.sqlite3.
    4. Start Django again.
"""

import shutil
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

PREFIX = 'hub_'


class Command(BaseCommand):
    help = 'Copy the database into the backups folder.'

    def add_arguments(self, parser):
        parser.add_argument('--keep', type=int, default=30, help='How many backups to keep (default 30).')
        parser.add_argument('--dir', default=None, help='Folder for backups (default: backups next to manage.py).')
        parser.add_argument(
            '--copy-dir', default=None,
            help='Second folder to copy the backup into (default: BACKUP_COPY_DIR from .env).',
        )

    def handle(self, *args, **options):
        if connection.vendor != 'sqlite':
            raise CommandError('backup_db only works with the SQLite database.')
        if options['keep'] < 1:
            raise CommandError('--keep must be at least 1.')

        folder = Path(options['dir']) if options['dir'] else Path(settings.BASE_DIR) / 'backups'
        folder.mkdir(parents=True, exist_ok=True)

        stamp = timezone.localtime().strftime('%Y-%m-%d_%H%M%S')
        target = folder / f'{PREFIX}{stamp}.sqlite3'

        connection.ensure_connection()
        destination = sqlite3.connect(target)
        try:
            connection.connection.backup(destination)  # page-by-page safe copy
        finally:
            destination.close()

        size_kb = target.stat().st_size / 1024
        self.stdout.write(self.style.SUCCESS(f'Backup saved: {target} ({size_kb:.0f} KB)'))
        self.remove_old(folder, options['keep'])

        copy_dir = options['copy_dir'] if options['copy_dir'] is not None else settings.BACKUP_COPY_DIR
        if copy_dir:
            self.copy_to(Path(copy_dir), target, options['keep'])

    def copy_to(self, folder, target, keep):
        """Put a second copy in another folder. A failure here never undoes the main backup."""
        try:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, folder / target.name)
        except OSError as error:
            self.stdout.write(self.style.WARNING(
                f'Could not copy the backup to {folder}: {error}. '
                'The backup in the normal folder is fine; check that folder is available.'
            ))
            return
        self.stdout.write(self.style.SUCCESS(f'Copy saved: {folder / target.name}'))
        self.remove_old(folder, keep)

    def remove_old(self, folder, keep):
        """Delete the oldest copies beyond `keep` (names sort by date)."""
        backups = sorted(folder.glob(f'{PREFIX}*.sqlite3'))
        for old in backups[:-keep]:
            old.unlink()
            self.stdout.write(f'Removed old backup: {old.name}')