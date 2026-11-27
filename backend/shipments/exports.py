"""
Export a filtered shipments list to an .xlsx file - exactly what the Shipments
page is showing (same filters). One row per shipment.
"""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from reports.services.excel_safety import keep_as_text

DELIVERED_BY_LABELS = {'rider': 'Rider', 'captain': 'Captain', '3pl': '3PL'}


def _delivered_on(shipment):
    value = getattr(shipment, 'delivered_on', None)  # annotated by with_attempt_count
    return value.isoformat() if value else ''


# (heading, how to read the value from a shipment)
COLUMNS = [
    ('Waybill Number', lambda s: s.waybill_number),
    ('Type', lambda s: s.get_shipment_type_display()),
    ('Status', lambda s: s.status.name),
    ('Reason', lambda s: s.failure_reason.name if s.failure_reason_id else ''),
    ('Reason note', lambda s: s.reason_note or ''),
    ('Notes', lambda s: s.notes or ''),
    ('Delivered on', _delivered_on),
    ('Delivered by', lambda s: DELIVERED_BY_LABELS.get(s.delivered_by, '')),
    ('Failed attempts', lambda s: getattr(s, 'attempt_count', 0) or 0),
    ('First seen', lambda s: s.first_seen_date.isoformat()),
    ('Last updated', lambda s: s.updated_at.strftime('%Y-%m-%d %H:%M')),
]

WIDTHS = [18, 8, 20, 22, 26, 26, 13, 13, 14, 12, 18]
HEADER_FILL = PatternFill('solid', fgColor='D9E1F2')


def build_shipments_xlsx(queryset):
    """Return the .xlsx bytes for the given shipment queryset."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Shipments'

    for col, (heading, _) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=1, column=col, value=heading)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal='center', vertical='center')

    for row, shipment in enumerate(queryset, start=2):
        for col, (_, getter) in enumerate(COLUMNS, start=1):
            sheet.cell(row=row, column=col, value=getter(shipment))

    for i, width in enumerate(WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(i)].width = width
    sheet.freeze_panes = 'A2'  # keep the header visible when scrolling

    keep_as_text(workbook)  # a note/reason starting with "=" stays text, not a formula
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()