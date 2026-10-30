"""
Import service: saves a confirmed scanner file as an ImportBatch.

Flow:
  1. preview_scan_file()  -> you look at the results (nothing saved)
  2. confirm_import()     -> this file: saves the batch and creates new shipments

What happens to each row on confirm:
  new                   -> a Shipment is created (status "Not Yet Checked"),
                           as Base or TEMU from its waybill prefix
  new, unknown prefix   -> created as the type you chose (unknown_type),
                           or recorded as invalid if you chose "skip"
  existing_outstanding  -> linked to the existing Shipment; nothing changes
  existing_closed       -> linked to the existing Shipment; nothing changes,
                           kept in the batch so you can review it
  duplicate_in_file     -> recorded only
  invalid               -> recorded only

Undo (undo_import): removes a wrong import and ONLY the shipments it created.
Shipments that were already in the system are never touched.
"""

import hashlib
from io import BytesIO

from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import ImportBatch, ImportRow, Shipment, StatusHistory
from .excel_reader import preview_scan_file
from .status_service import create_shipment


def file_fingerprint(data):
    """SHA-256 of the file's bytes. Same bytes -> same fingerprint."""
    return hashlib.sha256(data).hexdigest()


def find_previous_import(data):
    """Return the earlier batch for this exact file, or None."""
    return ImportBatch.objects.filter(file_hash=file_fingerprint(data)).first()


UNKNOWN_CHOICES = ('base', 'temu', 'skip')


@transaction.atomic
def confirm_import(file, reporting_date, column_index=None, file_name='scan.xlsx', unknown_type=None):
    """
    Save the file as an ImportBatch and create shipments for the new waybills.
    Everything happens in one transaction: if anything fails, nothing is saved.

    unknown_type: what to do with NEW waybills that start with neither 1 nor
    3034: 'base', 'temu' or 'skip'. Required only when such waybills exist.
    """
    if unknown_type is not None and unknown_type not in UNKNOWN_CHOICES:
        raise ValidationError('Choose Base, TEMU or Skip for waybills with an unknown prefix.')
    data = file.read()

    previous = find_previous_import(data)
    if previous:
        raise ValidationError(
            f'This exact file was already imported on {previous.imported_at:%d %b %Y} '
            f'for reporting date {previous.reporting_date:%d %b %Y}.'
        )

    # Classify again here, inside the transaction, so the result is current
    # even if something changed since you looked at the preview.
    preview = preview_scan_file(BytesIO(data), column_index=column_index)
    if preview['selected_column'] is None:
        raise ValidationError('Choose the waybill column before importing.')

    unknown = preview['new_by_type']['unknown']
    if unknown and unknown_type is None:
        raise ValidationError(
            f'{unknown} new waybill(s) start with neither 1 (Base) nor 3034 (TEMU). '
            'Choose Base, TEMU or Skip for them.'
        )

    # Skipped unknown waybills are recorded as invalid rows instead of shipments.
    for row in preview['rows']:
        if row['result'] == ImportRow.RESULT_NEW and row['shipment_type'] is None:
            if unknown_type == 'skip':
                row['result'] = ImportRow.RESULT_INVALID
                row['message'] = 'Skipped: waybill starts with neither 1 nor 3034.'
            else:
                row['shipment_type'] = unknown_type

    counts = {key: 0 for key in preview['counts']}
    new_by_type = {'base': 0, 'temu': 0}
    for row in preview['rows']:
        counts[row['result']] += 1
        if row['result'] == ImportRow.RESULT_NEW:
            new_by_type[row['shipment_type']] += 1
    batch = ImportBatch.objects.create(
        file_name=file_name,
        file_hash=file_fingerprint(data),
        reporting_date=reporting_date,
        column_index=preview['selected_column'],
        total_rows=preview['total_rows'],
        new_count=counts['new'],
        base_new_count=new_by_type['base'],
        temu_new_count=new_by_type['temu'],
        duplicate_in_file_count=counts['duplicate_in_file'],
        existing_outstanding_count=counts['existing_outstanding'],
        existing_closed_count=counts['existing_closed'],
        invalid_count=counts['invalid'],
    )

    # Existing shipments in this file, fetched with one query.
    existing_results = {ImportRow.RESULT_EXISTING_OUTSTANDING, ImportRow.RESULT_EXISTING_CLOSED}
    existing = {
        s.waybill_number: s
        for s in Shipment.objects.filter(
            waybill_number__in=[r['waybill'] for r in preview['rows'] if r['result'] in existing_results]
        )
    }

    import_rows = []
    for row in preview['rows']:
        shipment = None
        if row['result'] == ImportRow.RESULT_NEW:
            shipment = create_shipment(
                row['waybill'], first_seen_date=reporting_date, shipment_type=row['shipment_type'],
            )
        elif row['result'] in existing_results:
            shipment = existing[row['waybill']]

        import_rows.append(ImportRow(
            batch=batch,
            row_number=row['row_number'],
            waybill_number=row['waybill'][:255],
            result=row['result'],
            message=row['message'][:255],
            shipment=shipment,
        ))

    # bulk_create = one INSERT for all rows instead of one per row.
    ImportRow.objects.bulk_create(import_rows)
    return batch


def undo_blockers(batch):
    """
    Reasons this import cannot be undone (an empty list means it can).
    An undo must never change numbers you already worked on or sent.
    """
    # Imported here to avoid a circular import (reports imports shipments).
    from reports.models import DailyShipmentRecord

    created = Shipment.objects.filter(import_rows__batch=batch, import_rows__result=ImportRow.RESULT_NEW)
    blockers = []

    updated = [s.waybill_number for s in created if s.history.count() > 1]
    if updated:
        blockers.append(
            f'{len(updated)} shipment(s) from this import already have a status update '
            f'(e.g. {updated[0]}).'
        )

    in_final = (
        DailyShipmentRecord.objects
        .filter(shipment__in=created, day__state='finalized')
        .order_by('day__date')  # clear the default sort, or distinct() keeps duplicates
        .values_list('day__date', flat=True).distinct()
    )
    if in_final:
        dates = ', '.join(f'{d:%d %b %Y}' for d in in_final)
        blockers.append(f'Shipments from this import are in a finalized report ({dates}).')

    if ImportRow.objects.filter(shipment__in=created).exclude(batch=batch).exists():
        blockers.append('Shipments from this import appear in a later import. Undo that import first.')

    return blockers


@transaction.atomic
def undo_import(batch):
    """
    Delete an import and the shipments it created. All or nothing.
    Raises ValidationError (and deletes nothing) if undo_blockers() finds a reason not to.
    Returns how many shipments were removed.
    """
    from reports.models import DailyShipmentRecord

    batch = ImportBatch.objects.select_for_update().get(pk=batch.pk)
    blockers = undo_blockers(batch)
    if blockers:
        raise ValidationError(['This import cannot be undone:'] + blockers)

    created_ids = list(
        batch.rows.filter(result=ImportRow.RESULT_NEW).values_list('shipment_id', flat=True)
    )
    batch.delete()  # also deletes its rows
    DailyShipmentRecord.objects.filter(shipment_id__in=created_ids).delete()  # open days only (checked above)
    StatusHistory.objects.filter(shipment_id__in=created_ids).delete()
    Shipment.objects.filter(pk__in=created_ids).delete()
    return len(created_ids)