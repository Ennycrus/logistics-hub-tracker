"""
Day service: decides which shipments belong to a reporting day.

Base and TEMU are counted separately: every function takes a shipment_type
and only looks at shipments of that type.

Confirmed rules:
  Inbound      = shipments first scanned ON this date.
  Old Pending  = shipments first scanned BEFORE this date that were still
                 at the hub (not delivered, not rerouted) at the end of the
                 previous day. A re-scan of such a shipment does NOT make it
                 Inbound again.
  "Still at the hub" = category unchecked, outstanding or returned.
                 (Returned = back at the hub for another attempt.)

Everything is worked out from StatusHistory, using each change's
effective_date, so it gives the right answer even for past dates.
"""

import datetime

from django.core.exceptions import ValidationError
from django.db import transaction

from shipments.models import TYPE_TEMU, Shipment, StatusHistory
from shipments.services.excel_reader import OPEN_CATEGORIES  # one shared definition

from ..models import DailyShipmentRecord, ReportingDay


def statuses_as_of(shipment_ids, date):
    """
    Return {shipment_id: StatusOption} giving each shipment's status at the END
    of `date`, i.e. its latest history row with effective_date <= date.
    Shipments with no history up to that date are left out.
    """
    history = (
        StatusHistory.objects
        .filter(shipment_id__in=shipment_ids, effective_date__lte=date)
        .select_related('new_status')
        .order_by('effective_date', 'changed_at', 'pk')
    )
    result = {}
    for row in history:
        result[row.shipment_id] = row.new_status  # later rows overwrite earlier ones
    return result


def expected_records(date, shipment_type=TYPE_TEMU):
    """
    Work out {shipment_id: kind} for `date` and one shipment type, without saving anything.
    """
    expected = {}
    of_type = Shipment.objects.filter(shipment_type=shipment_type)

    # Inbound: first seen today.
    for shipment_id in of_type.filter(first_seen_date=date).values_list('pk', flat=True):
        expected[shipment_id] = DailyShipmentRecord.KIND_INBOUND

    # Old Pending: first seen earlier AND still at the hub at the end of the previous day.
    earlier_ids = list(of_type.filter(first_seen_date__lt=date).values_list('pk', flat=True))
    previous_day = date - datetime.timedelta(days=1)
    for shipment_id, status in statuses_as_of(earlier_ids, previous_day).items():
        if status.category in OPEN_CATEGORIES:
            expected[shipment_id] = DailyShipmentRecord.KIND_OLD_PENDING

    return expected


@transaction.atomic
def open_or_refresh_day(date, shipment_type=TYPE_TEMU):
    """
    Create the ReportingDay for `date` and one shipment type (if needed) and bring its shipment list
    up to date. Safe to run as often as you like on an OPEN day, e.g. after
    importing another scanner file. A FINALIZED day is never changed.

    Returns (day, summary) where summary counts what changed.
    """
    day, _ = ReportingDay.objects.select_for_update().get_or_create(
        date=date, shipment_type=shipment_type,
    )
    if not day.is_open:
        raise ValidationError(
            f'The {day.get_shipment_type_display()} report for {date} is finalized and cannot be changed.'
        )

    expected = expected_records(date, shipment_type)
    current = {r.shipment_id: r for r in day.records.all()}

    added = changed = removed = 0

    # Remove records that no longer qualify (e.g. history was corrected).
    for shipment_id, record in current.items():
        if shipment_id not in expected:
            record.delete()
            removed += 1

    to_create = []
    for shipment_id, kind in expected.items():
        record = current.get(shipment_id)
        if record is None:
            to_create.append(DailyShipmentRecord(day=day, shipment_id=shipment_id, kind=kind))
            added += 1
        elif record.kind != kind:
            record.kind = kind
            record.save(update_fields=['kind'])
            changed += 1
    DailyShipmentRecord.objects.bulk_create(to_create)

    summary = {
        'inbound': day.records.filter(kind=DailyShipmentRecord.KIND_INBOUND).count(),
        'old_pending': day.records.filter(kind=DailyShipmentRecord.KIND_OLD_PENDING).count(),
        'added': added,
        'changed': changed,
        'removed': removed,
    }
    return day, summary