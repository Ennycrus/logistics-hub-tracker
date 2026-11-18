"""
Calculations: the end-of-day figures for one reporting day.

Confirmed rules:
  Total Available = Inbound + Old Pending
  Delivered       = shipments whose status at the end of the day is "delivered"
  Current Day     = shipments still at the hub at the end of the day:
                    unchecked + outstanding (Pending, Unsuccessful) + returned
  Return          = shipments that came back to the hub THAT DAY: marked
                    "Delivery Unsuccessful" or "Returned to Hub" with that
                    day's date. They are ALSO inside Current Day, because they
                    will be attempted again (rule 4a). A shipment that failed
                    on an earlier day and was not taken out again is not
                    counted in Return again.
  Reasons         = the failure reasons of that day's Return only, so the two
                    always agree.
  Rerouted        = left the hub (category "left_hub": Rerouted to Another Hub,
                    Returned to Sender...); in neither Delivered nor Current Day.

So every shipment of the day lands in exactly one of:
  Delivered | Current Day | Rerouted
and those three must add up to Total Available. If they don't, a warning says why.

This file only READS. Nothing is saved.
"""

from collections import Counter

from core.models import HubConfig, StatusOption
from shipments.models import StatusHistory

from ..models import DailyShipmentRecord

C = StatusOption  # short alias for the category constants
AT_HUB = {C.CATEGORY_UNCHECKED, C.CATEGORY_OUTSTANDING, C.CATEGORY_RETURNED}


def latest_history_as_of(shipment_ids, date):
    """
    {shipment_id: StatusHistory row} = each shipment's last recorded change
    with effective_date <= date. That row holds the status AND the reason
    the shipment had at the end of that day.
    """
    rows = (
        StatusHistory.objects
        .filter(shipment_id__in=shipment_ids, effective_date__lte=date)
        .select_related('new_status', 'failure_reason')
        .order_by('effective_date', 'changed_at', 'pk')
    )
    latest = {}
    for row in rows:
        latest[row.shipment_id] = row  # later rows overwrite earlier ones
    return latest


def reasons_summary(history_rows, date):
    """
    Group failure reasons, e.g. "Customer unavailable - 6; Other (Gate locked) - 1".
    Only shipments that failed ON `date` are counted, so the reasons always
    explain that day's Return. Older failures still at the hub are left out
    (they are in Old Pending and Current Day).
    """
    counter = Counter()
    for row in history_rows:
        if row.new_status.category in AT_HUB and row.failure_reason_id and row.effective_date == date:
            label = row.failure_reason.name
            if row.failure_reason.is_other and row.reason_note:
                label = f'{label} ({row.reason_note})'
            counter[label] += 1

    # Most common first; ties in alphabetical order.
    ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return [{'reason': label, 'count': count} for label, count in ordered]


def calculate_day(day):
    """
    Work out every calculable figure for a ReportingDay.
    Returns a dict of figures, a reasons list and a list of warnings.
    """
    records = list(day.records.select_related('shipment'))
    kind_by_id = {r.shipment_id: r.kind for r in records}
    latest = latest_history_as_of(list(kind_by_id), day.date)

    inbound = sum(1 for k in kind_by_id.values() if k == DailyShipmentRecord.KIND_INBOUND)
    old_pending = len(kind_by_id) - inbound

    categories = Counter(row.new_status.category for row in latest.values())
    delivered = categories[C.CATEGORY_DELIVERED]
    # Return: came back to the hub today (unsuccessful or returned, dated today).
    returned = sum(
        1 for row in latest.values()
        if row.effective_date == day.date and (
            row.new_status.category == C.CATEGORY_RETURNED
            or (row.new_status.category == C.CATEGORY_OUTSTANDING and row.new_status.requires_reason)
        )
    )
    rerouted = categories[C.CATEGORY_LEFT_HUB]
    unchecked = categories[C.CATEGORY_UNCHECKED]
    current_day = sum(categories[c] for c in AT_HUB)
    unsuccessful = sum(
        1 for row in latest.values()
        if row.new_status.category == C.CATEGORY_OUTSTANDING and row.new_status.requires_reason
    )

    no_history = [r.shipment.waybill_number for r in records if r.shipment_id not in latest]
    total_available = inbound + old_pending

    figures = {
        'inbound': inbound,
        'old_pending': old_pending,
        'total_available': total_available,
        'delivered': delivered,
        'current_day': current_day,
        'return': returned,
        'rerouted': rerouted,
        'unsuccessful': unsuccessful,
        'unchecked': unchecked,
    }

    warnings = []
    if unchecked:
        warnings.append({
            'code': 'unchecked',
            'message': f'{unchecked} shipment(s) are still "Not Yet Checked". '
                       'They are counted in Current Day.',
        })
    if no_history:
        shown = ', '.join(no_history[:10])
        warnings.append({
            'code': 'no_history',
            'message': f'{len(no_history)} shipment(s) have no status history and are not '
                       f'counted anywhere: {shown}',
        })

    accounted = delivered + current_day + rerouted
    if accounted != total_available:
        warnings.append({
            'code': 'does_not_reconcile',
            'message': f'Delivered ({delivered}) + Current Day ({current_day}) + '
                       f'Left hub ({rerouted}) = {accounted}, but Total Available is '
                       f'{total_available}. Difference: {total_available - accounted}.',
        })

    config = HubConfig.get()
    reasons = reasons_summary(latest.values(), day.date)
    if config.reasons_format == HubConfig.REASONS_FORMAT_GROUPED:
        reasons_text = '; '.join(f"{r['reason']} - {r['count']}" for r in reasons)
    else:
        reasons_text = ''  # written by hand on the report (next step)

    return {
        'date': day.date,
        'hub_name': config.hub_name,
        'figures': figures,
        'reasons': reasons,
        'reasons_text': reasons_text,
        'reconciliation': {
            'delivered': delivered,
            'current_day': current_day,
            'rerouted': rerouted,
            'accounted_for': accounted,
            'total_available': total_available,
            'balanced': accounted == total_available,
        },
        'warnings': warnings,
    }