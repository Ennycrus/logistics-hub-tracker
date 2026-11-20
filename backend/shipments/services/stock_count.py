"""
Stock count: compare what is physically on the shelves with what the app says.

You scan every parcel in the hub (gun scanner file, or a pasted list). This
compares that scan with the app and sorts every waybill into one group:

  matched     scanned, and the app says it is at the hub        -> all good
  missing     the app says it is at the hub, but it was NOT     -> lost, misplaced,
              scanned                                              or left without an update
  closed      scanned, but the app says delivered / left hub    -> wrong status
  not_in_app  scanned, but the app has never seen it            -> never imported

Nothing is saved or changed here: it only reports. The file uses exactly the
same reading rules as an import (column detection, several waybills in one
cell, other columns, formula cells).

shipment_type: count only TEMU or only Base (e.g. separate shelves). Scanned
parcels of the other type are then left out instead of being reported.
"""

from django.db.models import Max
from django.utils import timezone

from ..models import Shipment
from .excel_reader import OPEN_CATEGORIES, preview_scan_file
from .shipment_types import detect_type

# Passed through from the file reading, so the page can show the same warnings as Import.
FILE_KEYS = [
    'columns', 'selected_column', 'has_header', 'total_rows', 'waybills_found', 'other_sheets',
    'formulas_without_value', 'all_columns', 'elsewhere', 'message',
]


def shipment_row(shipment, today):
    last = shipment.last_change or shipment.first_seen_date
    return {
        'shipment_id': shipment.pk,
        'waybill': shipment.waybill_number,
        'shipment_type': shipment.shipment_type,
        'status': shipment.status.name,
        'arrived': shipment.first_seen_date,
        'last_update': last,
        'days_since_update': (today - last).days,
    }


def stock_count(file, column_index=None, file_name='', all_columns=False, shipment_type=None):
    preview = preview_scan_file(file, column_index=column_index, file_name=file_name, all_columns=all_columns)
    result = {key: preview.get(key) for key in FILE_KEYS}
    result['shipment_type'] = shipment_type or ''
    if preview['selected_column'] is None:
        return result

    today = timezone.localdate()
    scanned = {}  # waybill -> row result ('new', 'existing_outstanding', 'existing_closed')
    other_type = 0
    for row in preview['rows']:
        if row['result'] not in ('new', 'existing_outstanding', 'existing_closed'):
            continue  # duplicates and invalid cells are not parcels
        row_type = row['shipment_type'] or detect_type(row['waybill'])
        if shipment_type and row_type and row_type != shipment_type:
            other_type += 1
            continue
        scanned[row['waybill']] = row['result']

    shipments = Shipment.objects.select_related('status').annotate(last_change=Max('history__effective_date'))
    if shipment_type:
        shipments = shipments.filter(shipment_type=shipment_type)

    known = {
        s.waybill_number: s
        for s in shipments.filter(waybill_number__in=[w for w, r in scanned.items() if r != 'new'])
    }
    missing = (
        shipments.filter(status__category__in=OPEN_CATEGORIES)
        .exclude(waybill_number__in=list(scanned))
        .order_by('first_seen_date', 'waybill_number')
    )

    result.update({
        'scanned': len(scanned),
        'other_type': other_type,
        'matched': sum(1 for r in scanned.values() if r == 'existing_outstanding'),
        'missing': [shipment_row(s, today) for s in missing],
        'closed': [
            shipment_row(known[w], today) for w, r in sorted(scanned.items())
            if r == 'existing_closed' and w in known
        ],
        'not_in_app': [
            {'waybill': w, 'shipment_type': detect_type(w)}
            for w, r in sorted(scanned.items()) if r == 'new'
        ],
    })
    result['pending_in_app'] = result['matched'] + len(result['missing'])
    return result