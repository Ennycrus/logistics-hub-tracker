"""
Excel export: writes a FINALIZED report in the company's 11-column layout.

Only the frozen snapshot is used, so the file is identical every time you
download it, even if shipment statuses change later.

Layout:
    Row 1   Daily Hub Report - TEMU   (or - Base)
    Row 2   Date: 28 Oct 2026
    Row 3   (corrections only) Corrected report - version 2: <reason>
    Row 5   HUBS | Inbound | Old Pending | ... | Reasons   <- headers
    Row 6   the figures
"""

from io import BytesIO

from django.core.exceptions import ValidationError
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# (column heading, where the value comes from). The order must match the company sheet.
COLUMNS = [
    ('HUBS', 'hub_name'),
    ('Inbound', 'inbound'),
    ('Old Pending', 'old_pending'),
    ('Total Available', 'total_available'),
    ('Delivered', 'delivered'),
    ('Current Day', 'current_day'),
    ('Return', 'return'),
    ('No of Vans', 'vans'),
    ('No of Bike', 'bikes'),
    ('No of 3PL', 'third_party'),
    ('Reasons', 'reasons_text'),
]

HEADER_ROW = 5
DATA_ROW = 6

THIN = Side(style='thin', color='808080')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill('solid', fgColor='D9E1F2')


def report_values(report):
    """The 11 values in column order, taken only from the frozen report."""
    source = {
        **report.figures,
        'hub_name': report.hub_name,
        'vans': report.vans,
        'bikes': report.bikes,
        'third_party': report.third_party,
        'reasons_text': report.reasons_text,
    }
    return [source[key] for _, key in COLUMNS]


def build_workbook(report):
    """Return an openpyxl Workbook for a finalized DailyReport."""
    if not report.is_finalized:
        raise ValidationError('Only a finalized report can be exported.')

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = report.day.date.strftime('%d-%m-%Y')

    sheet['A1'] = f'Daily Hub Report - {report.day.get_shipment_type_display()}'
    sheet['A1'].font = Font(bold=True, size=14)
    sheet['A2'] = f'Date: {report.day.date:%d %b %Y}'
    sheet['A2'].font = Font(bold=True)
    if report.corrects_id:
        sheet['A3'] = (
            f'Corrected report - version {report.version}: {report.correction_reason}'
        )
        sheet['A3'].font = Font(italic=True, color='C00000')

    # Header row
    for index, (heading, _) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=HEADER_ROW, column=index, value=heading)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.border = BORDER
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    # Data row
    for index, value in enumerate(report_values(report), start=1):
        cell = sheet.cell(row=DATA_ROW, column=index, value=value)
        cell.border = BORDER
        if isinstance(value, int):
            cell.number_format = '0'
            cell.alignment = Alignment(horizontal='center', vertical='top')
        else:
            cell.alignment = Alignment(vertical='top', wrap_text=True)

    # Column widths: wide enough for the heading; Reasons gets extra room.
    for index, (heading, key) in enumerate(COLUMNS, start=1):
        width = 45 if key == 'reasons_text' else max(len(heading) + 4, 12)
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.row_dimensions[HEADER_ROW].height = 30

    return workbook


def export_report_bytes(report):
    """The .xlsx file as bytes (used by the command now, and the website later)."""
    buffer = BytesIO()
    build_workbook(report).save(buffer)
    return buffer.getvalue()


def export_file_name(report):
    """e.g. Akala_Express_TEMU_2026-10-28.xlsx, or ..._v2.xlsx for a correction."""
    hub = ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in report.hub_name) or 'hub'
    kind = report.day.get_shipment_type_display()
    suffix = f'_v{report.version}' if report.version > 1 else ''
    return f'{hub}_{kind}_{report.day.date:%Y-%m-%d}{suffix}.xlsx'