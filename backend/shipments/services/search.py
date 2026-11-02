"""
Waybill search, the same everywhere in the app.

    exactly 4 digits  -> waybills ENDING with them   ("3584" finds ...3584 only)
    anything else     -> waybills CONTAINING it      ("91573" finds 303491573584)

Four digits means "the last four of the waybill", the way they are usually read out.
"""

import re

from django.db.models import Q

LAST_FOUR = re.compile(r'^\d{4}$')


def waybill_search(text, field='waybill_number'):
    """A Q filter for `text`, or None when there is nothing to search for."""
    text = (text or '').strip()
    if not text:
        return None
    if LAST_FOUR.match(text):
        return Q(**{f'{field}__endswith': text})
    return Q(**{f'{field}__icontains': text})