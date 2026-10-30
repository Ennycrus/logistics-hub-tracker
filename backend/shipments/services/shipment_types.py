"""
Which report a waybill belongs to, worked out from how its number starts:

    3034...  -> TEMU
    1...     -> Base
    anything else -> unknown (you choose Base, TEMU or Skip when importing)

To change the rules, edit PREFIX_RULES only. Longer prefixes are checked
first, so a more specific rule always wins.
"""

from ..models import TYPE_BASE, TYPE_TEMU

PREFIX_RULES = [
    ('3034', TYPE_TEMU),
    ('1', TYPE_BASE),
]


def detect_type(waybill):
    """Return 'base', 'temu', or None if the prefix matches neither."""
    waybill = (waybill or '').strip()
    for prefix, shipment_type in sorted(PREFIX_RULES, key=lambda rule: -len(rule[0])):
        if waybill.startswith(prefix):
            return shipment_type
    return None