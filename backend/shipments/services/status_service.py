"""
Status service: the ONLY place where a shipment is created or its status changes.

Every function here does two things together, inside one database transaction:
  1. updates the Shipment's current state, and
  2. writes a StatusHistory row describing the change.
If either part fails, both are undone, so history can never fall out of step.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import StatusOption

from ..models import DELIVERED_BY_CHOICES, SHIPMENT_TYPE_CHOICES, TYPE_TEMU, Shipment, StatusHistory
from .shipment_types import detect_type


def get_unchecked_status():
    """The status every new shipment starts with (category 'unchecked')."""
    status = (
        StatusOption.objects
        .filter(category=StatusOption.CATEGORY_UNCHECKED, is_active=True)
        .order_by('sort_order')
        .first()
    )
    if status is None:
        raise ValidationError('No active "unchecked" status exists. Add one in Settings.')
    return status


@transaction.atomic
def create_shipment(waybill_number, first_seen_date=None, shipment_type=TYPE_TEMU):
    """
    Create a new shipment with the 'unchecked' status and its first history row.
    Raises ValidationError if the waybill is empty or already exists, or if
    shipment_type contradicts the waybill prefix (e.g. a "1..." waybill as TEMU).
    """
    first_seen_date = first_seen_date or timezone.localdate()
    waybill_number = (waybill_number or '').strip()

    if shipment_type not in dict(SHIPMENT_TYPE_CHOICES):
        raise ValidationError({'shipment_type': f'Unknown shipment type "{shipment_type}".'})
    detected = detect_type(waybill_number)
    if detected and detected != shipment_type:
        raise ValidationError({
            'shipment_type': f'Waybill {waybill_number} is a {detected.upper()} waybill, not {shipment_type.upper()}.'
        })

    if Shipment.objects.filter(waybill_number=waybill_number).exists():
        raise ValidationError({'waybill_number': f'Waybill {waybill_number} already exists.'})

    shipment = Shipment(
        waybill_number=waybill_number,
        shipment_type=shipment_type,
        status=get_unchecked_status(),
        first_seen_date=first_seen_date,
    )
    shipment.full_clean()  # runs the rules in Shipment.clean()
    shipment.save()

    StatusHistory.objects.create(
        shipment=shipment,
        old_status=None,  # None = "this is when the shipment was created"
        new_status=shipment.status,
        effective_date=first_seen_date,
        note='Shipment created',
    )
    return shipment


def is_only_adding_who(shipment, new_status, delivered_by):
    """
    True when the change only fills in who delivered an already-delivered
    shipment that had nobody recorded. That needs no note and keeps the
    delivery's own date, so it never moves a delivery to another day.
    """
    return bool(
        shipment.status_id == new_status.pk
        and new_status.category == StatusOption.CATEGORY_DELIVERED
        and not shipment.delivered_by
        and (delivered_by or '').strip()
    )


@transaction.atomic
def change_status(
    shipment,
    new_status,
    failure_reason=None,
    reason_note='',
    note='',
    effective_date=None,
    delivered_by='',
):
    """
    Change a shipment's current status and record the change in history.

    - Reason fields are cleared automatically when the new status does not
      need a reason (e.g. switching from Unsuccessful to Delivered).
    - If nothing actually changed, no history row is written.
    - Changing a shipment that is already DELIVERED needs a note explaining
      why (e.g. "Marked delivered by mistake"). The note is kept in history.
    - delivered_by ('rider', 'captain' or '3pl') records who delivered it.
      It is kept only for a delivered status and cleared otherwise.
    - Filling in who delivered a shipment that is already delivered (and had
      nobody recorded) needs no note, and keeps the original delivery date,
      so the delivery stays in the week it really happened.
    - The date cannot be before the shipment arrived (its first scan).
    - Returns True if a change was recorded, False if nothing changed.
    """
    effective_date = effective_date or timezone.localdate()

    if not new_status.is_active:
        raise ValidationError({'status': f'"{new_status.name}" is switched off and cannot be used.'})

    # Lock this shipment's row until the transaction ends, so two saves
    # at the same moment cannot interleave.
    shipment = Shipment.objects.select_for_update().get(pk=shipment.pk)

    # Don't carry irrelevant details: no reason unless the status needs one,
    # and no reason note unless the reason is "Other".
    if not new_status.requires_reason:
        failure_reason = None
    if failure_reason is None or not failure_reason.is_other:
        reason_note = ''
    reason_note = (reason_note or '').strip()

    delivered_by = (delivered_by or '').strip()
    if new_status.category != StatusOption.CATEGORY_DELIVERED:
        delivered_by = ''
    elif delivered_by and delivered_by not in dict(DELIVERED_BY_CHOICES):
        raise ValidationError({'delivered_by': 'Choose Rider, Captain or 3PL.'})

    nothing_changed = (
        shipment.status_id == new_status.pk
        and shipment.failure_reason_id == (failure_reason.pk if failure_reason else None)
        and shipment.reason_note == reason_note
        and shipment.delivered_by == delivered_by
    )
    if nothing_changed:
        return False

    # Only adding who delivered it: no note needed, and the delivery keeps its date.
    only_adding_who = is_only_adding_who(shipment, new_status, delivered_by)
    if only_adding_who:
        last = shipment.history.order_by('-effective_date', '-changed_at', '-pk').first()
        if last:
            effective_date = last.effective_date

    if effective_date < shipment.first_seen_date:
        raise ValidationError({'effective_date': (
            f'This shipment only arrived on {shipment.first_seen_date:%d %b %Y}, '
            'so the date cannot be earlier than that.'
        )})

    # Delivered is normally final. Undoing it is allowed, but never silently.
    note = (note or '').strip()
    if shipment.status.category == StatusOption.CATEGORY_DELIVERED and not note and not only_adding_who:
        raise ValidationError(
            {'note': 'This shipment is already delivered. Write a note explaining the change.'}
        )

    old_status = shipment.status
    shipment.status = new_status
    shipment.failure_reason = failure_reason
    shipment.reason_note = reason_note
    shipment.delivered_by = delivered_by
    shipment.full_clean()  # raises ValidationError -> transaction rolls back
    shipment.save()

    StatusHistory.objects.create(
        shipment=shipment,
        old_status=old_status,
        new_status=new_status,
        failure_reason=failure_reason,
        reason_note=reason_note,
        delivered_by=delivered_by,
        note=note,
        effective_date=effective_date,
    )
    return True


# The most shipments one bulk update may change (a full day is about 150-500).
MAX_BULK = 500


def bulk_change_status(
    shipment_ids,
    new_status,
    failure_reason=None,
    reason_note='',
    note='',
    effective_date=None,
    delivered_by='',
):
    """
    Give many shipments the same new status, ALL OR NOTHING.

    Each shipment goes through change_status(), so every normal rule applies
    (reasons, "Other" notes, the delivered-needs-a-note rule) and every change
    gets its own history row.

    If even one shipment fails a rule, nothing is saved and the failures are
    returned, so a half-applied bulk update can never happen.

    Returns {'changed': n, 'unchanged': n, 'failures': [...]}.
    """
    ids = list(dict.fromkeys(shipment_ids))  # remove repeats, keep the order
    if not ids:
        raise ValidationError('Choose at least one shipment.')
    if len(ids) > MAX_BULK:
        raise ValidationError(f'You can update at most {MAX_BULK} shipments at once.')

    shipments = {s.pk: s for s in Shipment.objects.filter(pk__in=ids)}
    missing = [pk for pk in ids if pk not in shipments]
    if missing:
        raise ValidationError(f'{len(missing)} selected shipment(s) no longer exist. Reload the page.')

    changed = unchanged = 0
    failures = []

    with transaction.atomic():
        for pk in ids:
            shipment = shipments[pk]
            try:
                # change_status() has its own inner transaction (a "savepoint"),
                # so one failure is undone without breaking the loop.
                if change_status(
                    shipment, new_status,
                    failure_reason=failure_reason, reason_note=reason_note,
                    note=note, effective_date=effective_date, delivered_by=delivered_by,
                ):
                    changed += 1
                else:
                    unchanged += 1
            except ValidationError as error:
                failures.append({
                    'id': pk,
                    'waybill_number': shipment.waybill_number,
                    'error': ' '.join(error.messages),
                })

        if failures:
            transaction.set_rollback(True)  # undo every change made in this loop
            return {'changed': 0, 'unchanged': 0, 'failures': failures}

    return {'changed': changed, 'unchanged': unchanged, 'failures': []}