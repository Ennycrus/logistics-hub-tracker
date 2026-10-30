"""
Weekly delivery summary, worked out from FINALIZED reports only, so the week
always matches what you sent to the company.

A delivery week runs Monday to Saturday (6 days). Sunday is not a delivery day.

For one shipment type (TEMU or Base):
  each day      delivered, total available, and that day's rate
                (delivered / total available)
  the week      delivered      = Mon + ... + Sat delivered
                available      = Monday's Old Pending (waiting at the start
                                 of the week) + every Inbound from Mon to Sat
                rate           = delivered / available

Why not add up the daily "Total Available"? A shipment that waits three days
is in three of them, so the sum would count it three times.

Days that are not finalized are listed as missing and the week is marked
incomplete. If Monday is missing, the week's starting Old Pending is unknown,
so no weekly rate is given.
"""

import datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from shipments.models import TYPE_TEMU

from .report_service import current_report

DELIVERY_DAYS = 6  # Monday to Saturday


def week_start(date):
    """The Monday of the delivery week containing `date` (a Sunday belongs to the week before it)."""
    return date - datetime.timedelta(days=date.weekday())


def rate(delivered, available):
    """Percentage with 1 decimal place, or None when nothing was available."""
    if not available:
        return None
    return round(delivered * 100 / available, 1)


def weekly_summary(date, shipment_type=TYPE_TEMU):
    monday = week_start(date)
    days = []
    for offset in range(DELIVERY_DAYS):
        day = monday + datetime.timedelta(days=offset)
        report = current_report(day, shipment_type)
        if report is None:
            days.append({'date': day, 'weekday': day.strftime('%A'), 'finalized': False,
                         'version': None, 'inbound': None, 'old_pending': None,
                         'total_available': None, 'delivered': None, 'rate': None})
            continue
        f = report.figures
        days.append({
            'date': day,
            'weekday': day.strftime('%A'),
            'finalized': True,
            'version': report.version,
            'inbound': f['inbound'],
            'old_pending': f['old_pending'],
            'total_available': f['total_available'],
            'delivered': f['delivered'],
            'rate': rate(f['delivered'], f['total_available']),
        })

    done = [d for d in days if d['finalized']]
    delivered = sum(d['delivered'] for d in done)
    monday_done = days[0]['finalized']
    opening = days[0]['old_pending'] if monday_done else None
    new_inbound = sum(d['inbound'] for d in done)
    available = opening + new_inbound if monday_done else None

    return {
        'shipment_type': shipment_type,
        'week_start': monday,
        'week_end': monday + datetime.timedelta(days=DELIVERY_DAYS - 1),
        'days': days,
        'missing': [d['date'] for d in days if not d['finalized']],
        'complete': len(done) == DELIVERY_DAYS,
        'totals': {
            'delivered': delivered,
            'opening_pending': opening,
            'new_inbound': new_inbound,
            'available': available,
            'rate': rate(delivered, available) if monday_done else None,
        },
    }


# --- Excel -----------------------------------------------------------------

THIN = Side(style='thin', color='808080')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill('solid', fgColor='D9E1F2')
TOTAL_FILL = PatternFill('solid', fgColor='F2F2F2')


def weekly_workbook_bytes(summary, hub_name=''):
    """The weekly summary as an .xlsx file (bytes)."""
    label = 'TEMU' if summary['shipment_type'] == TYPE_TEMU else 'Base'
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = f'Week {summary["week_start"]:%d-%m-%Y}'

    sheet['A1'] = f'Weekly Delivery - {label}'
    sheet['A1'].font = Font(bold=True, size=14)
    sheet['A2'] = f'{hub_name}  Week {summary["week_start"]:%d %b} - {summary["week_end"]:%d %b %Y} (Mon-Sat)'.strip()
    sheet['A2'].font = Font(bold=True)
    if not summary['complete']:
        missing = ', '.join(f'{d:%a %d %b}' for d in summary['missing'])
        sheet['A3'] = f'Incomplete: not finalized - {missing}'
        sheet['A3'].font = Font(italic=True, color='C00000')

    headers = ['Day', 'Date', 'Total Available', 'Delivered', 'Delivery rate']
    for col, heading in enumerate(headers, start=1):
        cell = sheet.cell(row=5, column=col, value=heading)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.border = BORDER
        cell.alignment = Alignment(horizontal='center')

    row = 6
    for d in summary['days']:
        values = [d['weekday'], d['date'].strftime('%d %b %Y')]
        if d['finalized']:
            values += [d['total_available'], d['delivered'],
                       None if d['rate'] is None else d['rate'] / 100]
        else:
            values += ['not finalized', None, None]
        for col, value in enumerate(values, start=1):
            cell = sheet.cell(row=row, column=col, value=value)
            cell.border = BORDER
            if col == 5 and value is not None:
                cell.number_format = '0.0%'
        row += 1

    t = summary['totals']
    total_rows = [
        ('Delivered this week', t['delivered'], None),
        ('Waiting on Monday (Old Pending)', t['opening_pending'], None),
        ('New inbound Mon-Sat', t['new_inbound'], None),
        ('Available this week', t['available'], None),
        ('Weekly delivery rate', None if t['rate'] is None else t['rate'] / 100, '0.0%'),
    ]
    row += 1
    for label_text, value, fmt in total_rows:
        sheet.cell(row=row, column=1, value=label_text).font = Font(bold=True)
        cell = sheet.cell(row=row, column=4, value=value if value is not None else 'n/a')
        cell.font = Font(bold=True)
        if fmt and value is not None:
            cell.number_format = fmt
        for col in range(1, 6):
            sheet.cell(row=row, column=col).fill = TOTAL_FILL
        row += 1

    for col, width in zip('ABCDE', [32, 14, 16, 12, 14]):
        sheet.column_dimensions[col].width = width

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def weekly_file_name(summary, hub_name=''):
    hub = ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in hub_name) or 'hub'
    label = 'TEMU' if summary['shipment_type'] == TYPE_TEMU else 'Base'
    return f'{hub}_{label}_week_{summary["week_start"]:%Y-%m-%d}.xlsx'