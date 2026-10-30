"""
Enter the manual figures for a day's report draft and show the preview.

Usage examples:
    python manage.py report_inputs --date 2026-10-28
    python manage.py report_inputs --date 2026-10-28 --vans 2 --bikes 6 --3pl 3
    python manage.py report_inputs --date 2026-10-28 --notes "Rain in the afternoon"
    python manage.py report_inputs --date 2026-10-28 --adjust delivered 40 "Counted at the gate"
    python manage.py report_inputs --date 2026-10-28 --clear-adjust delivered

Only the options you give are changed. Run with just --date to see the preview.
"""

import datetime

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from reports.services.report_service import get_or_create_draft, preview, save_draft


def print_preview(command, draft):
    """Print a report draft. Also used by finalize_report."""
    data = preview(draft)
    f = data['figures']
    label = f'v{draft.version} draft' + (' (correction)' if draft.corrects_id else '')

    def show(value):
        return '-' if value is None else value

    command.stdout.write(command.style.SUCCESS(f"{data['hub_name']} - {draft.day.date} - {label}"))
    rows = [
        ('Inbound', 'inbound'), ('Old Pending', 'old_pending'),
        ('Total Available', 'total_available'), ('Delivered', 'delivered'),
        ('Current Day', 'current_day'), ('Return', 'return'),
    ]
    for title, key in rows:
        marker = '  (adjusted)' if key in draft.adjustments else ''
        command.stdout.write(f'  {title + ":":<18}{f[key]}{marker}')
    command.stdout.write(f"  {'No of Vans:':<18}{show(draft.vans)}")
    command.stdout.write(f"  {'No of Bike:':<18}{show(draft.bikes)}")
    command.stdout.write(f"  {'No of 3PL:':<18}{show(draft.third_party)}")
    command.stdout.write(f"  {'Reasons:':<18}{data['reasons_text'] or '-'}")
    if draft.notes:
        command.stdout.write(f"  {'Notes:':<18}{draft.notes}")

    if data['problems']:
        command.stdout.write(command.style.ERROR('\nMust fix before finalizing:'))
        for problem in data['problems']:
            command.stdout.write(command.style.ERROR(f'  - {problem}'))
    if data['warnings']:
        command.stdout.write(command.style.WARNING('\nWarnings:'))
        for warning in data['warnings']:
            command.stdout.write(command.style.WARNING(f"  - {warning['message']}"))
    return data


class Command(BaseCommand):
    help = "Enter manual figures for a day's report and show the preview."

    def add_arguments(self, parser):
        parser.add_argument('--date', required=True, help='Format YYYY-MM-DD')
        parser.add_argument('--vans', type=int)
        parser.add_argument('--bikes', type=int)
        parser.add_argument('--3pl', dest='third_party', type=int)
        parser.add_argument('--notes')
        parser.add_argument('--reasons', help='Your own Reasons text (replaces the grouped one)')
        parser.add_argument('--adjust', nargs=3, action='append', metavar=('FIELD', 'VALUE', 'NOTE'),
                            help='Override a calculated figure, with a note')
        parser.add_argument('--clear-adjust', action='append', metavar='FIELD',
                            help='Remove an earlier override')

    def handle(self, *args, **options):
        try:
            date = datetime.date.fromisoformat(options['date'])
        except ValueError:
            raise CommandError('Date must look like 2026-10-28.')

        adjust = {}
        for field, value, note in options['adjust'] or []:
            try:
                adjust[field] = (int(value), note)
            except ValueError:
                raise CommandError(f'{field}: "{value}" is not a whole number.')

        try:
            draft = get_or_create_draft(date)
            save_draft(
                draft,
                vans=options['vans'],
                bikes=options['bikes'],
                third_party=options['third_party'],
                notes=options['notes'],
                reasons_text=options['reasons'],
                adjust=adjust,
                clear_adjust=options['clear_adjust'],
            )
        except ValidationError as error:
            raise CommandError(' '.join(error.messages))

        print_preview(self, draft)