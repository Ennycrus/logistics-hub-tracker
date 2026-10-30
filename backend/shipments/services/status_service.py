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

from ..models import SHIPMENT_TYPE_CHOICES, TYPE_TEMU, Shipment, StatusHistory
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


@transaction.atomic
def change_status(
    shipment,
    new_status,
    failure_reason=None,
    reason_note='',
    note='',
    effective_date=None,
):
    """
    Change a shipment's current status and record the change in history.

    - Reason fields are cleared automatically when the new status does not
      need a reason (e.g. switching from Unsuccessful to Delivered).
    - If nothing actually changed, no history row is written.
    - Changing a shipment that is already DELIVERED needs a note explaining
      why (e.g. "Marked delivered by mistake"). The note is kept in history.
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

    nothing_changed = (
        shipment.status_id == new_status.pk
        and shipment.failure_reason_id == (failure_reason.pk if failure_reason else None)
        and shipment.reason_note == reason_note
    )
    if nothing_changed:
        return False

    # Delivered is normally final. Undoing it is allowed, but never silently.
    note = (note or '').strip()
    if shipment.status.category == StatusOption.CATEGORY_DELIVERED and not note:
        raise ValidationError(
            {'note': 'This shipment is already delivered. Write a note explaining the change.'}
        )

    old_status = shipment.status
    shipment.status = new_status
    shipment.failure_reason = failure_reason
    shipment.reason_note = reason_note
    shipment.full_clean()  # raises ValidationError -> transaction rolls back
    shipment.save()

    StatusHistory.objects.create(
        shipment=shipment,
        old_status=old_status,
        new_status=new_status,
        failure_reason=failure_reason,
        reason_note=reason_note,
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
                    note=note, effective_date=effective_date,
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