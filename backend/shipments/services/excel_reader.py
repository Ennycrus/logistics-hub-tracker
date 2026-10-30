"""
Excel reader: reads a gun-scanner spreadsheet and PREVIEWS it.

Nothing is saved to the database here. This file only answers:
  - Which column holds the waybill numbers?
  - What is in each row, and how should it be treated?

Every row gets one result:
  new                   -> waybill not in the system yet
  duplicate_in_file     -> appeared earlier in this same file
  existing_outstanding  -> already in the system and still at the hub
                           (normal: it reappears because it is outstanding)
  existing_closed       -> already in the system but delivered / left the hub
                           (unusual: needs your review)
  invalid               -> empty or badly formatted waybill

Every row also gets a shipment type: 'base' or 'temu' from the waybill prefix
(existing shipments keep the type they already have), or None when a NEW
waybill matches neither prefix, so you can choose for it when importing.
"""

import re
import zipfile

from django.core.exceptions import ValidationError
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException

from core.models import StatusOption

from ..models import Shipment
from .shipment_types import detect_type

MAX_ROWS = 5000

# Header words that suggest "this column holds waybill numbers".
HEADER_KEYWORDS = ['waybill', 'way bill', 'tracking', 'awb', 'parcel', 'barcode', 'shipment']

# Letters, digits and dashes only, 1-64 characters.
WAYBILL_PATTERN = re.compile(r'^[A-Za-z0-9-]{1,64}$')

# Categories that mean "still the hub's responsibility".
OPEN_CATEGORIES = {
    StatusOption.CATEGORY_UNCHECKED,
    StatusOption.CATEGORY_OUTSTANDING,
    StatusOption.CATEGORY_RETURNED,
}


def cell_to_text(value):
    """
    Turn a cell value into waybill text.
    Text cells are kept exactly (so leading zeros survive).
    Number cells are converted without a trailing '.0'.
    """
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def looks_like_header(text):
    lowered = text.lower()
    return any(word in lowered for word in HEADER_KEYWORDS)


def read_rows(file):
    """Open the workbook and return its non-blank rows as lists of values."""
    try:
        workbook = load_workbook(file, read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError):
        raise ValidationError('This is not a valid Excel (.xlsx) file.')

    sheet = workbook.active
    rows = []
    for row_number, values in enumerate(sheet.iter_rows(values_only=True), start=1):
        if all(v is None or str(v).strip() == '' for v in values):
            continue  # skip completely blank rows
        rows.append((row_number, list(values)))
        if len(rows) > MAX_ROWS:
            workbook.close()
            raise ValidationError(f'The file has more than {MAX_ROWS} rows.')
    workbook.close()

    if not rows:
        raise ValidationError('The spreadsheet is empty.')
    return rows


def find_header(rows):
    """
    If the first row contains a waybill-like heading, treat it as a header.
    Returns (header_values or None, index_of_waybill_column or None).
    """
    first_values = [cell_to_text(v) for v in rows[0][1]]
    for index, text in enumerate(first_values):
        if text and looks_like_header(text):
            return first_values, index
    return None, None


def preview_scan_file(file, column_index=None):
    """
    Read the file and classify every row. Saves nothing.

    column_index: 0-based column to use. Leave as None for automatic detection.
    """
    rows = read_rows(file)
    width = max(len(values) for _, values in rows)

    header, detected_index = find_header(rows)
    data_rows = rows[1:] if header else rows

    columns = []
    for index in range(width):
        label = header[index] if header and index < len(header) and header[index] else ''
        columns.append({
            'index': index,
            'label': label or f'Column {get_column_letter(index + 1)}',
        })

    # Which column to use: your choice > header match > the only column.
    if column_index is not None:
        if not 0 <= column_index < width:
            raise ValidationError(f'Column {column_index} does not exist in this file.')
        selected = column_index
    elif detected_index is not None:
        selected = detected_index
    elif width == 1:
        selected = 0
    else:
        selected = None

    result = {
        'columns': columns,
        'selected_column': selected,
        'has_header': header is not None,
        'total_rows': len(data_rows),
        'counts': {},
        'rows': [],
    }
    if selected is None:
        result['message'] = 'Could not detect the waybill column. Please choose one.'
        return result

    # Look up every waybill already in the database with ONE query.
    texts = [
        cell_to_text(values[selected]) if selected < len(values) else ''
        for _, values in data_rows
    ]
    existing = {
        s.waybill_number: s
        for s in Shipment.objects.filter(waybill_number__in=[t for t in texts if t])
        .select_related('status')
    }

    seen = set()
    counts = {key: 0 for key in [
        'new', 'duplicate_in_file', 'existing_outstanding', 'existing_closed', 'invalid',
    ]}
    # New shipments by type. 'unknown' = new waybills matching neither prefix.
    new_by_type = {'base': 0, 'temu': 0, 'unknown': 0}

    for (row_number, _), waybill in zip(data_rows, texts):
        if not waybill:
            outcome, message = 'invalid', 'Empty waybill cell.'
        elif not WAYBILL_PATTERN.match(waybill):
            outcome, message = 'invalid', 'Unexpected characters or too long.'
        elif waybill in seen:
            outcome, message = 'duplicate_in_file', 'Already listed earlier in this file.'
        elif waybill in existing:
            status = existing[waybill].status
            if status.category in OPEN_CATEGORIES:
                outcome = 'existing_outstanding'
                message = f'Already in the system, still at hub ({status.name}).'
            else:
                outcome = 'existing_closed'
                message = f'Already in the system as "{status.name}". Please review.'
        else:
            outcome, message = 'new', ''

        if outcome in ('existing_outstanding', 'existing_closed'):
            shipment_type = existing[waybill].shipment_type
        elif outcome == 'new':
            shipment_type = detect_type(waybill)
            new_by_type[shipment_type or 'unknown'] += 1
        else:
            shipment_type = None

        if waybill and outcome != 'invalid':
            seen.add(waybill)
        counts[outcome] += 1
        result['rows'].append({
            'row_number': row_number,
            'waybill': waybill,
            'result': outcome,
            'message': message,
            'shipment_type': shipment_type,
        })

    result['counts'] = counts
    result['new_by_type'] = new_by_type
    return result