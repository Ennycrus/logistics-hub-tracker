"""
Report service: drafts, manual inputs, finalizing and corrections.

Rules:
  - Vans, Bikes and 3PL are always entered by you. The app never guesses them.
  - A calculated figure can be overridden, but only with a note, and the
    override is recorded so you can always see what was changed.
  - Total Available is never overridden directly. It is always
    Inbound + Old Pending (after any overrides to those two).
  - Warnings don't block finalizing (rule 5), but you must accept them,
    and they are stored with the report.
  - A finalized report is never edited. A correction creates a new version.
  - Base and TEMU have separate reports: each function takes a shipment_type.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from shipments.models import TYPE_TEMU

from ..models import DailyReport, ReportingDay
from .calculations import calculate_day
from .day_service import open_or_refresh_day

# The calculated figures you are allowed to override by hand.
ADJUSTABLE = ['inbound', 'old_pending', 'delivered', 'current_day', 'return']


def apply_adjustments(calculated, adjustments):
    """Combine calculated figures with manual overrides. Total Available is recomputed."""
    figures = dict(calculated)
    for field, change in adjustments.items():
        figures[field] = change['value']
    figures['total_available'] = figures['inbound'] + figures['old_pending']
    return figures


def get_or_create_draft(date, shipment_type=TYPE_TEMU):
    """
    Return the open draft for `date` and one shipment type, creating it if needed.
    The day's shipment list is refreshed first while the day is still open.
    """
    day = ReportingDay.objects.filter(date=date, shipment_type=shipment_type).first()
    if day is None or day.is_open:
        day, _ = open_or_refresh_day(date, shipment_type)

    draft = day.reports.filter(is_finalized=False).first()
    if draft:
        return draft
    if not day.is_open:
        raise ValidationError(
            f'The {day.get_shipment_type_display()} report for {date} is finalized. '
            'Start a correction to change it.'
        )
    return DailyReport.objects.create(day=day, version=1)


@transaction.atomic
def save_draft(draft, vans=None, bikes=None, third_party=None,
               notes=None, reasons_text=None, adjust=None, clear_adjust=None):
    """
    Update a draft. Only the values you pass are changed.

    adjust:       {field: (value, note)} to override calculated figures
    clear_adjust: [field, ...] to remove earlier overrides
    """
    if draft.is_finalized:
        raise ValidationError('A finalized report cannot be edited.')

    for name, value in [('vans', vans), ('bikes', bikes), ('third_party', third_party)]:
        if value is not None:
            if value < 0:
                raise ValidationError({name: 'Cannot be negative.'})
            setattr(draft, name, value)

    if notes is not None:
        draft.notes = notes.strip()
    if reasons_text is not None:
        draft.reasons_text = reasons_text.strip()

    adjustments = dict(draft.adjustments)
    for field in clear_adjust or []:
        adjustments.pop(field, None)
    for field, (value, note) in (adjust or {}).items():
        if field not in ADJUSTABLE:
            raise ValidationError(
                f'"{field}" cannot be adjusted. Choose from: {", ".join(ADJUSTABLE)}.'
            )
        if value < 0:
            raise ValidationError(f'{field} cannot be negative.')
        if not (note or '').strip():
            raise ValidationError(f'Write a note explaining why {field} was changed.')
        adjustments[field] = {'value': value, 'note': note.strip()}
    draft.adjustments = adjustments

    draft.save()
    return draft


def preview(draft):
    """Everything the report would contain if finalized now. Saves nothing."""
    result = calculate_day(draft.day)
    calculated = result['figures']
    figures = apply_adjustments(calculated, draft.adjustments)

    # Grouped reasons are filled in automatically unless you typed your own.
    reasons_text = draft.reasons_text or result['reasons_text']

    problems = []  # these BLOCK finalizing
    for label, value in [('No of Vans', draft.vans), ('No of Bike', draft.bikes),
                         ('No of 3PL', draft.third_party)]:
        if value is None:
            problems.append(f'{label} has not been entered.')

    warnings = list(result['warnings'])
    for field, change in draft.adjustments.items():
        warnings.append({
            'code': 'manual_adjustment',
            'message': f'{field} changed by hand from {calculated[field]} to '
                       f'{change["value"]}: {change["note"]}',
        })

    return {
        'hub_name': result['hub_name'],
        'calculated': calculated,
        'figures': figures,
        'reasons_text': reasons_text,
        'reconciliation': result['reconciliation'],
        'warnings': warnings,
        'problems': problems,
    }


@transaction.atomic
def finalize(draft, accept_warnings=False):
    """
    Freeze the draft into a permanent snapshot and mark the day finalized.
    """
    draft = DailyReport.objects.select_for_update().get(pk=draft.pk)
    if draft.is_finalized:
        raise ValidationError('This report is already finalized.')

    data = preview(draft)
    if data['problems']:
        raise ValidationError(data['problems'])
    if data['warnings'] and not accept_warnings:
        raise ValidationError(
            'This report has warnings. Review them and accept them to finalize.'
        )

    draft.calculated = data['calculated']
    draft.figures = data['figures']
    draft.warnings = data['warnings']
    draft.reasons_text = data['reasons_text']
    draft.hub_name = data['hub_name']
    draft.is_finalized = True
    draft.finalized_at = timezone.now()
    draft.save()

    day = draft.day
    day.state = ReportingDay.STATE_FINALIZED
    day.save(update_fields=['state', 'updated_at'])
    return draft


def current_report(date, shipment_type=TYPE_TEMU):
    """The latest finalized version for a date and type (what the company should have), or None."""
    return (
        DailyReport.objects
        .filter(day__date=date, day__shipment_type=shipment_type, is_finalized=True)
        .order_by('-version')
        .first()
    )


@transaction.atomic
def start_correction(date, reason, shipment_type=TYPE_TEMU):
    """
    Create a new draft version that corrects the latest finalized report.
    The original stays exactly as it was.
    """
    if not (reason or '').strip():
        raise ValidationError('Write a reason for the correction.')

    original = current_report(date, shipment_type)
    if original is None:
        raise ValidationError(f'There is no finalized report for {date} to correct.')
    if original.day.reports.filter(is_finalized=False).exists():
        raise ValidationError(f'A correction for {date} is already in progress.')

    return DailyReport.objects.create(
        day=original.day,
        version=original.version + 1,
        corrects=original,
        correction_reason=reason.strip(),
        # Start from the original's inputs so you only change what was wrong.
        vans=original.vans,
        bikes=original.bikes,
        third_party=original.third_party,
        notes=original.notes,
        adjustments=original.adjustments,
    )