"""attempts.py
Failed delivery attempts, and the "ready to initiate return" reminder.

A failed attempt = one "Delivery Unsuccessful" entry in a shipment's history
(a status that is Outstanding AND needs a failure reason). When a shipment
reaches settings.RETURN_AFTER_ATTEMPTS failed attempts and is still at the hub,
the app reminds you to set it to Initiated Return. It never changes the status
itself: the reminder is only a nudge.
"""

from django.conf import settings
from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce

from core.models import StatusOption

from ..models import StatusHistory

# Still the hub's responsibility (so the reminder still applies).
AT_HUB = (
    StatusOption.CATEGORY_UNCHECKED,
    StatusOption.CATEGORY_OUTSTANDING,
    StatusOption.CATEGORY_RETURNED,
)


def failed_attempts(shipment):
    """How many times this shipment has been recorded Delivery Unsuccessful."""
    return shipment.history.filter(
        new_status__category=StatusOption.CATEGORY_OUTSTANDING,
        new_status__requires_reason=True,
    ).count()


def with_attempt_count(queryset):
    """
    Add an `attempt_count` to each shipment in the queryset, counted with a
    subquery so it stays correct even next to other history aggregates.
    """
    failed = (
        StatusHistory.objects
        .filter(
            shipment=OuterRef('pk'),
            new_status__category=StatusOption.CATEGORY_OUTSTANDING,
            new_status__requires_reason=True,
        )
        .values('shipment')
        .annotate(n=Count('*'))
        .values('n')
    )
    return queryset.annotate(
        attempt_count=Coalesce(Subquery(failed, output_field=IntegerField()), 0),
    )


def is_ready_for_return(count, category):
    return count >= settings.RETURN_AFTER_ATTEMPTS and category in AT_HUB