"""
The Saturday hub report for the manager (one per Mon-Sat week).

  1. TEMU pending in the hub now   - TEMU shipments whose status is still open
                                     (Not Yet Checked, Pending/Unsuccessful, Returned)
  2. Base pending in the hub now   - the same for Base
  3. Delivered this week           - shipments marked Delivered with a date in
                                     the week (and still delivered),
                                     split by who delivered: Rider, Captain, 3PL
  4. Not in the hub (awaiting      - shipments out with riders, no result yet
     update)                         (the Not Yet Checked category). These are
                                     ALSO inside items 1 and 2, because pending
                                     means "not delivered yet".
  5. Fuel used (litres)            - added up from the daily logs of the week,
                                     riders and captains separately
  6. Incidents / escalations /     - every daily log note of the week, by day,
     challenges / difficulties       plus any extra notes typed on Saturday

Fuel and incidents are typed in each day on the Daily Report page (DailyHubLog).
Every save of a day is kept (DailyHubLogChange), so changes leave a trace.
Pressing Save freezes everything, so a saved report never changes later.
Saving again adds a new version; the earlier ones are kept.

Sundays: the report goes out on Saturday evening, so anything dated on a
Sunday (deliveries, fuel, incidents) is counted in the NEXT week's report.
Nothing done on a Sunday is ever left out.

Stuck shipments: not delivered and no status change for STALE_DAYS or more.
They are still counted in items 1, 2 and 4, but the page warns about them.

Check for you (not sent to the manager): item 3 is compared with the
Delivered figures of the finalized daily reports (TEMU + Base) for the week.
"""

import datetime
from collections import Counter
from decimal import Decimal
from io import BytesIO

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from core.models import HubConfig, StatusOption
from shipments.models import (
    DELIVERED_BY_3PL, DELIVERED_BY_CAPTAIN, DELIVERED_BY_RIDER, TYPE_BASE, TYPE_TEMU,
    Shipment, StatusHistory,
)
from shipments.services.excel_reader import OPEN_CATEGORIES

from ..models import DailyHubLog, DailyHubLogChange, WeeklyHubReport
from .report_service import current_report
from .weekly import DELIVERY_DAYS, week_start, weekly_summary

STALE_DAYS = 7  # warn about shipments with no status change for this many days


def week_end(monday):
    return monday + datetime.timedelta(days=DELIVERY_DAYS - 1)


def sunday_before(monday):
    """The Sunday just before this week's Monday; it belongs to this week's report."""
    return monday - datetime.timedelta(days=1)


def litres(value):
    """Decimal -> plain number for JSON (2.50 -> 2.5), or None."""
    if value is None:
        return None
    value = Decimal(value).normalize()
    return int(value) if value == value.to_integral() else float(value)


# --- Items 1-4: counted from the shipments ------------------------------------

def pending_counts():
    """Open shipments per type right now: {'temu': n, 'base': n}."""
    rows = (
        Shipment.objects.filter(status__category__in=OPEN_CATEGORIES)
        .values('shipment_type').annotate(n=Count('pk'))
    )
    counts = {TYPE_TEMU: 0, TYPE_BASE: 0}
    for row in rows:
        counts[row['shipment_type']] = row['n']
    return counts


def not_in_hub_count():
    """Shipments out with riders with no result yet (Not Yet Checked)."""
    return Shipment.objects.filter(status__category=StatusOption.CATEGORY_UNCHECKED).count()


def stale_count(days=STALE_DAYS):
    """Not delivered yet, and the last status change was `days` or more days ago."""
    cutoff = timezone.localdate() - datetime.timedelta(days=days)
    return (
        Shipment.objects.filter(status__category__in=OPEN_CATEGORIES)
        .annotate(last_change=Max('history__effective_date'))
        .filter(last_change__lte=cutoff)
        .count()
    )


def delivered_counts(monday):
    """
    Delivered from the Sunday before to Saturday, split by who delivered.
    Each shipment counts once: its last change up to Saturday must be a
    Delivered status dated inside the week.
    """
    first = sunday_before(monday)
    saturday = week_end(monday)
    rows = (
        StatusHistory.objects.filter(effective_date__lte=saturday)
        .select_related('new_status')
        .order_by('effective_date', 'changed_at', 'pk')
    )
    latest = {}
    for row in rows:
        latest[row.shipment_id] = row  # later rows overwrite earlier ones

    by = Counter()
    for row in latest.values():
        if row.new_status.category == StatusOption.CATEGORY_DELIVERED and row.effective_date >= first:
            by[row.delivered_by or 'not_recorded'] += 1
    return {
        'riders': by[DELIVERED_BY_RIDER],
        'captains': by[DELIVERED_BY_CAPTAIN],
        'third_party': by[DELIVERED_BY_3PL],
        'not_recorded': by['not_recorded'],
        'total': sum(by.values()),
    }


# --- Items 5-6: from the daily logs -------------------------------------------

def week_logs(monday):
    """The daily logs from the Sunday before to Saturday."""
    return list(DailyHubLog.objects.filter(date__range=(sunday_before(monday), week_end(monday))))


def days_so_far(monday):
    """Monday up to Saturday, or up to today while the week is still running."""
    last = min(week_end(monday), timezone.localdate())
    return [monday + datetime.timedelta(days=n) for n in range((last - monday).days + 1)]


def fuel_totals(logs, monday):
    """
    Litres used this week. A total stays None (not entered) when no day of
    the week has a figure for it, so "0" always means someone typed 0.
    `missing_days` = days so far with no fuel typed in, so a forgotten day shows.
    """
    def total(field):
        values = [getattr(log, field) for log in logs if getattr(log, field) is not None]
        return litres(sum(values)) if values else None

    entered = {log.date for log in logs
               if log.fuel_riders_litres is not None or log.fuel_captains_litres is not None}
    days = days_so_far(monday)  # Mon-Sat; a Sunday entry still adds to the totals
    return {
        'riders': total('fuel_riders_litres'),
        'captains': total('fuel_captains_litres'),
        'days_entered': len([d for d in days if d in entered]),
        'days_so_far': len(days),
        'missing_days': [d.isoformat() for d in days if d not in entered],
    }


def incident_list(logs):
    """[{'date': '2026-11-10', 'text': ...}] for every day with an incident note."""
    return [{'date': log.date.isoformat(), 'text': log.incidents.strip()}
            for log in logs if log.incidents.strip()]


def daily_reports_check(monday, delivered_total):
    """
    Item 3 compared with the finalized daily reports (TEMU + Base, Mon-Sat,
    plus the Sunday before if a report was finalized for it).
    They can differ when a daily report was adjusted by hand, or when a
    delivery was recorded after that day's report was finalized.
    """
    delivered = 0
    missing = 0
    for shipment_type in (TYPE_TEMU, TYPE_BASE):
        summary = weekly_summary(monday, shipment_type)
        delivered += summary['totals']['delivered']
        missing += len([d for d in summary['missing'] if d <= timezone.localdate()])
        sunday = current_report(sunday_before(monday), shipment_type)
        if sunday:
            delivered += sunday.figures.get('delivered', 0)
    return {
        'delivered': delivered,
        'missing_reports': missing,  # daily reports (TEMU + Base) not finalized yet
        'matches': delivered == delivered_total,
    }


def live_figures(monday):
    pending = pending_counts()
    logs = week_logs(monday)
    delivered = delivered_counts(monday)
    return {
        'temu_pending': pending[TYPE_TEMU],
        'base_pending': pending[TYPE_BASE],
        'delivered': delivered,
        'not_in_hub': not_in_hub_count(),
        'stale': {'count': stale_count(), 'days': STALE_DAYS},
        'fuel': fuel_totals(logs, monday),
        'incidents': incident_list(logs),
        'daily_reports': daily_reports_check(monday, delivered['total']),
    }


def days_of_week(monday):
    """
    Each day Mon-Sat with its log (for the table on the Saturday page).
    The Sunday before is listed first, but only when something was entered for it.
    """
    logs = {log.date: log for log in week_logs(monday)}
    sunday = sunday_before(monday)
    dates = ([sunday] if sunday in logs else []) + [
        monday + datetime.timedelta(days=offset) for offset in range(DELIVERY_DAYS)
    ]
    days = []
    for day in dates:
        log = logs.get(day)
        days.append({
            'date': day,
            'weekday': day.strftime('%A'),
            'fuel_riders_litres': litres(log.fuel_riders_litres) if log else None,
            'fuel_captains_litres': litres(log.fuel_captains_litres) if log else None,
            'incidents': log.incidents if log else '',
        })
    return days


# --- The report ---------------------------------------------------------------

def incident_lines(figures, extra_notes):
    """Item 6: one line per day with a note, then the extra notes."""
    lines = []
    for item in figures['incidents']:
        day = datetime.date.fromisoformat(item['date'])
        lines.append(f'{day:%a %d %b}: {" ".join(item["text"].split())}')
    if extra_notes.strip():
        lines.append(' '.join(extra_notes.split()))
    return lines


def report_text(report):
    """The report as plain text, ready to paste into WhatsApp or an email."""
    f = report['figures']
    d = f['delivered']
    split = f'Riders {d["riders"]}, Captains {d["captains"]}, 3PLs {d["third_party"]}'
    if d['not_recorded']:
        split += f', not recorded {d["not_recorded"]}'

    def fuel(value):
        return 'not entered' if value is None else f'{value} litres'

    fuel_days = ''
    fuel_info = f['fuel']
    if fuel_info.get('missing_days') and fuel_info['days_entered']:
        fuel_days = f' (entered for {fuel_info["days_entered"]} of {fuel_info["days_so_far"]} days)'

    title = 'Weekly Report' + (f' - {report["hub_name"]}' if report['hub_name'] else '')
    item6 = '6. Incidents/Escalations/Challenges/Difficulties:'
    incidents = incident_lines(f, report['extra_notes'])
    return '\n'.join([
        title,
        f'Week: {report["week_start"]:%a %d %b} - {report["week_end"]:%a %d %b %Y}',
        '',
        f'1. TEMU shipments pending in hub: {f["temu_pending"]}',
        f'2. Base shipments pending in hub: {f["base_pending"]}',
        f'3. Shipments delivered: {d["total"]} ({split})',
        f'4. Shipments not in hub (awaiting update): {f["not_in_hub"]} (already included in 1 and 2)',
        f'5. Fuel used: Riders {fuel(f["fuel"]["riders"])}, Captains {fuel(f["fuel"]["captains"])}{fuel_days}',
        *([item6, *[f'   - {line}' for line in incidents]] if incidents else [f'{item6} None']),
    ])


def weekly_hub_report(date, version=None):
    """
    The report for the week containing `date`.
    Saved -> the latest saved version (or the `version` asked for), frozen.
    Not saved yet -> live figures.
    """
    monday = week_start(date)
    versions = WeeklyHubReport.objects.filter(week_start=monday, saved_at__isnull=False)
    if version is not None:
        saved = versions.filter(version=version).first()
        if saved is None:
            raise ValidationError(f'There is no version {version} for the week of {monday:%d %b %Y}.')
    else:
        saved = versions.order_by('-version').first()
    is_saved = saved is not None
    live = live_figures(monday)
    report = {
        'week_start': monday,
        'week_end': week_end(monday),
        'saved': is_saved,
        'version': saved.version if is_saved else None,
        'versions': versions.count(),
        'saved_at': saved.saved_at if is_saved else None,
        'hub_name': saved.hub_name if is_saved else HubConfig.get().hub_name,
        'extra_notes': saved.extra_notes if saved else '',
        'figures': saved.figures if is_saved else live,
        'live_figures': live,
        'days': days_of_week(monday),
    }
    report['text'] = report_text(report)
    return report


@transaction.atomic
def save_weekly_hub_report(date, extra_notes=''):
    """
    Freeze every figure as it is right now, with the extra notes.
    Each save is a NEW version; earlier versions are never changed.
    """
    monday = week_start(date)
    last = (
        WeeklyHubReport.objects.select_for_update()
        .filter(week_start=monday).order_by('-version').first()
    )
    WeeklyHubReport.objects.create(
        week_start=monday,
        version=(last.version + 1) if last else 1,
        extra_notes=(extra_notes or '').strip(),
        figures=live_figures(monday),
        hub_name=HubConfig.get().hub_name,
        saved_at=timezone.now(),
    )
    return weekly_hub_report(date)


def saved_reports():
    """Every saved version of every week, newest week (and version) first."""
    return [
        {
            'week_start': r.week_start,
            'week_end': week_end(r.week_start),
            'version': r.version,
            'saved_at': r.saved_at,
            'delivered': r.figures.get('delivered', {}).get('total'),
            'temu_pending': r.figures.get('temu_pending'),
            'base_pending': r.figures.get('base_pending'),
        }
        for r in WeeklyHubReport.objects.filter(saved_at__isnull=False)
    ]


# --- Daily log (fuel and incidents for one day) -------------------------------

def daily_log(date):
    """One day's fuel and incidents, with every earlier save (newest first)."""
    log = DailyHubLog.objects.filter(date=date).first()
    changes = list(log.changes.all()) if log else []
    return {
        'date': date,
        'fuel_riders_litres': litres(log.fuel_riders_litres) if log else None,
        'fuel_captains_litres': litres(log.fuel_captains_litres) if log else None,
        'incidents': log.incidents if log else '',
        'updated_at': log.updated_at if log else None,
        'changes': [
            {
                'saved_at': c.saved_at,
                'fuel_riders_litres': litres(c.fuel_riders_litres),
                'fuel_captains_litres': litres(c.fuel_captains_litres),
                'incidents': c.incidents,
            }
            for c in changes
        ],
    }


@transaction.atomic
def save_daily_log(date, fuel_riders_litres=None, fuel_captains_litres=None, incidents=''):
    """Save one day's figures. A save that changes something is added to its change list."""
    incidents = (incidents or '').strip()
    log, created = DailyHubLog.objects.select_for_update().get_or_create(date=date)
    same = (
        not created
        and log.fuel_riders_litres == fuel_riders_litres
        and log.fuel_captains_litres == fuel_captains_litres
        and log.incidents == incidents
    )
    if not same:
        log.fuel_riders_litres = fuel_riders_litres
        log.fuel_captains_litres = fuel_captains_litres
        log.incidents = incidents
        log.save()
        DailyHubLogChange.objects.create(
            log=log,
            fuel_riders_litres=fuel_riders_litres,
            fuel_captains_litres=fuel_captains_litres,
            incidents=incidents,
        )
    return daily_log(date)


# --- Excel --------------------------------------------------------------------

THIN = Side(style='thin', color='808080')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill('solid', fgColor='D9E1F2')


def weekly_hub_workbook_bytes(report):
    f = report['figures']
    d = f['delivered']
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = f'Week {report["week_start"]:%d-%m-%Y}'

    sheet['A1'] = 'Weekly Report' + (f' - {report["hub_name"]}' if report['hub_name'] else '')
    sheet['A1'].font = Font(bold=True, size=14)
    sheet['A2'] = f'Week {report["week_start"]:%a %d %b} - {report["week_end"]:%a %d %b %Y}'
    sheet['A2'].font = Font(bold=True)
    if not report['saved']:
        sheet['A3'] = 'Draft: not saved yet. Figures are as at download time.'
        sheet['A3'].font = Font(italic=True, color='C00000')
    elif report['versions'] > 1:
        saved = timezone.localtime(report['saved_at'])
        sheet['A3'] = f'Version {report["version"]} of {report["versions"]}, saved {saved:%d %b %Y %H:%M}'
        sheet['A3'].font = Font(italic=True, color='808080')

    incidents = incident_lines(f, report['extra_notes'])
    rows = [
        ('#', 'Item', 'Value'),
        (1, 'TEMU shipments pending in hub', f['temu_pending']),
        (2, 'Base shipments pending in hub', f['base_pending']),
        (3, 'Shipments delivered - total', d['total']),
        ('', '   by Riders', d['riders']),
        ('', '   by Captains', d['captains']),
        ('', '   by 3PLs', d['third_party']),
    ]
    if d['not_recorded']:
        rows.append(('', '   not recorded', d['not_recorded']))
    rows += [
        (4, 'Shipments not in hub (awaiting update) - already included in 1 and 2', f['not_in_hub']),
        (5, 'Fuel used by Riders (litres)', f['fuel']['riders']),
        ('', 'Fuel used by Captains (litres)', f['fuel']['captains']),
        (6, 'Incidents / Escalations / Challenges / Difficulties', '\n'.join(incidents) or 'None'),
    ]
    for r, values in enumerate(rows, start=5):
        for c, value in enumerate(values, start=1):
            cell = sheet.cell(row=r, column=c, value=value)
            cell.border = BORDER
            cell.alignment = Alignment(vertical='top', wrap_text=(c == 3))
            if r == 5:
                cell.font = Font(bold=True)
                cell.fill = HEADER_FILL

    sheet.column_dimensions['A'].width = 5
    sheet.column_dimensions['B'].width = 50
    sheet.column_dimensions['C'].width = 60

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def weekly_hub_file_name(report):
    hub = (report['hub_name'] or 'Hub').replace(' ', '_')
    version = f'_v{report["version"]}' if report['versions'] > 1 else ''
    return f'{hub}_Weekly_Report_{report["week_start"]:%Y-%m-%d}{version}.xlsx'