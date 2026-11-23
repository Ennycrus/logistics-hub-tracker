"""
Trends: how the hub has been doing over the last several weeks, and which
failure reasons come up most. Everything is counted straight from the status
history, so it needs no finalized reports.

    GET /api/reports/trends/?type=temu&weeks=8&reason_days=30

    {
      "type": "temu",
      "weeks": [                      # oldest first, Monday-Sunday weeks
        {"week_start": "2026-09-29", "delivered": 310, "unsuccessful": 44},
        ...
      ],
      "top_reasons": {
        "days": 30,
        "total": 120,
        "reasons": [{"name": "Customer unavailable", "count": 51}, ...]
      }
    }

delivered  = different shipments delivered that week.
unsuccessful = failed delivery attempts recorded that week (a shipment can
               fail on several days, so each counts).
"""

import datetime

from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import StatusOption

from shipments.models import SHIPMENT_TYPE_CHOICES, TYPE_TEMU, StatusHistory

MAX_WEEKS = 26
MAX_REASON_DAYS = 180


def _int_param(params, name, default, low, high):
    raw = params.get(name)
    if raw is None or raw == '':
        return default
    if not str(raw).isdigit():
        raise ValidationError({name: 'Must be a whole number.'})
    return max(low, min(high, int(raw)))


class TrendsView(APIView):
    def get(self, request):
        params = request.query_params
        shipment_type = params.get('type', TYPE_TEMU)
        if shipment_type not in dict(SHIPMENT_TYPE_CHOICES):
            raise ValidationError({'type': 'Use temu or base.'})
        weeks = _int_param(params, 'weeks', 8, 1, MAX_WEEKS)
        reason_days = _int_param(params, 'reason_days', 30, 1, MAX_REASON_DAYS)

        today = timezone.localdate()
        this_monday = today - datetime.timedelta(days=today.weekday())

        base = StatusHistory.objects.filter(shipment__shipment_type=shipment_type)

        week_rows = []
        for i in range(weeks - 1, -1, -1):  # oldest first
            start = this_monday - datetime.timedelta(days=7 * i)
            end = start + datetime.timedelta(days=6)
            in_week = base.filter(effective_date__range=(start, end))
            delivered = (
                in_week.filter(new_status__category=StatusOption.CATEGORY_DELIVERED)
                .values('shipment').distinct().count()
            )
            unsuccessful = in_week.filter(
                new_status__category=StatusOption.CATEGORY_OUTSTANDING,
                new_status__requires_reason=True,
            ).count()
            week_rows.append({
                'week_start': start.isoformat(),
                'delivered': delivered,
                'unsuccessful': unsuccessful,
            })

        since = today - datetime.timedelta(days=reason_days - 1)
        reason_qs = (
            base.filter(
                new_status__category=StatusOption.CATEGORY_OUTSTANDING,
                new_status__requires_reason=True,
                failure_reason__isnull=False,
                effective_date__gte=since,
            )
            .values('failure_reason__name')
            .annotate(count=Count('*'))
            .order_by('-count', 'failure_reason__name')
        )
        reasons = [{'name': r['failure_reason__name'], 'count': r['count']} for r in reason_qs]

        return Response({
            'type': shipment_type,
            'weeks': week_rows,
            'top_reasons': {
                'days': reason_days,
                'total': sum(r['count'] for r in reasons),
                'reasons': reasons,
            },
        })