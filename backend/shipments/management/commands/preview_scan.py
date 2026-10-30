"""
Try the Excel reader on a real file from the terminal.

Usage:
    python manage.py preview_scan "C:\\path\\to\\scan.xlsx"
    python manage.py preview_scan "C:\\path\\to\\scan.xlsx" --column 1

Nothing is saved to the database.
"""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from shipments.services.excel_reader import preview_scan_file


class Command(BaseCommand):
    help = 'Preview a gun-scanner Excel file without saving anything.'

    def add_arguments(self, parser):
        parser.add_argument('path', help='Path to the .xlsx file')
        parser.add_argument('--column', type=int, default=None,
                            help='0-based column number to use (A=0, B=1, ...)')

    def handle(self, *args, **options):
        try:
            with open(options['path'], 'rb') as file:
                result = preview_scan_file(file, column_index=options['column'])
        except FileNotFoundError:
            raise CommandError('File not found. Check the path (use quotes if it has spaces).')
        except ValidationError as error:
            raise CommandError(error.messages[0])

        self.stdout.write('Columns found:')
        for col in result['columns']:
            marker = '  <- selected' if col['index'] == result['selected_column'] else ''
            self.stdout.write(f"  [{col['index']}] {col['label']}{marker}")

        if result['selected_column'] is None:
            self.stdout.write(self.style.WARNING(result['message']))
            self.stdout.write('Run again with --column N.')
            return

        self.stdout.write(f"\nHeader row: {'yes' if result['has_header'] else 'no'}")
        self.stdout.write(f"Rows read:  {result['total_rows']}\n")
        for key, value in result['counts'].items():
            self.stdout.write(f'  {key:<22} {value}')

        problems = [r for r in result['rows'] if r['result'] != 'new']
        if problems:
            self.stdout.write('\nRows needing attention:')
            for row in problems[:50]:
                self.stdout.write(
                    f"  row {row['row_number']:>4}  {row['waybill'] or '(empty)':<20} "
                    f"{row['result']:<22} {row['message']}"
                )
            if len(problems) > 50:
                self.stdout.write(f'  ...and {len(problems) - 50} more')