"""
The TEMU return-waybill email.

When a shipment is sent back to the sender (a "left hub" status) you type its
NEW return waybill. This lists those returns so you can email the partner the
Old -> New waybill table, then mark them as emailed so they drop off the list.

    GET  /api/returns/pending/?type=temu
        Shipments with a return waybill that have NOT been emailed yet, oldest
        first. Also returns the recipients and subject from Hub settings, so the
        website can open a ready-made email.

    POST /api/returns/mark-emailed/   {"shipment_ids": [1, 2, 3]}
        Stamp those shipments as emailed (now), so the next list excludes them.

Nothing is emailed by the server: the website opens the email in your own mail
app for you to review and send.
"""

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import HubConfig, StatusOption

from .models import SHIPMENT_TYPE_CHOICES, TYPE_TEMU, Shipment


def pending_returns(shipment_type):
    """Shipments that have left the hub with a return waybill and are not yet emailed."""
    queryset = (
        Shipment.objects
        .filter(
            status__category=StatusOption.CATEGORY_LEFT_HUB,
            return_emailed_at__isnull=True,
        )
        .exclude(return_waybill='')
        .select_related('status')
        .order_by('first_seen_date', 'waybill_number')
    )
    if shipment_type:
        queryset = queryset.filter(shipment_type=shipment_type)
    return queryset


def missing_waybill_returns(shipment_type):
    """Left-the-hub shipments still waiting for a return waybill, so they can't be emailed yet."""
    queryset = (
        Shipment.objects
        .filter(
            status__category=StatusOption.CATEGORY_LEFT_HUB,
            return_emailed_at__isnull=True,
            return_waybill='',
        )
        .select_related('status')
        .order_by('first_seen_date', 'waybill_number')
    )
    if shipment_type:
        queryset = queryset.filter(shipment_type=shipment_type)
    return queryset


class ReturnsPending(APIView):
    def get(self, request):
        shipment_type = request.query_params.get('type', TYPE_TEMU)
        if shipment_type not in dict(SHIPMENT_TYPE_CHOICES):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'type': 'Use temu or base.'})
        rows = [
            {
                'id': s.pk,
                'waybill_number': s.waybill_number,
                'return_waybill': s.return_waybill,
                'status_name': s.status.name,
                'arrived': s.first_seen_date,
            }
            for s in pending_returns(shipment_type)
        ]
        missing = [
            {
                'id': s.pk,
                'waybill_number': s.waybill_number,
                'status_name': s.status.name,
                'arrived': s.first_seen_date,
            }
            for s in missing_waybill_returns(shipment_type)
        ]
        config = HubConfig.get()
        return Response({
            'count': len(rows),
            'results': rows,
            'missing_count': len(missing),
            'missing': missing,
            'email_to': config.return_email_to,
            'email_subject': config.return_email_subject,
        })


class MarkReturnsEmailed(APIView):
    class InputSerializer(serializers.Serializer):
        shipment_ids = serializers.ListField(
            child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=500,
        )

    def post(self, request):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = (
            Shipment.objects
            .filter(pk__in=serializer.validated_data['shipment_ids'], return_emailed_at__isnull=True)
            .exclude(return_waybill='')
            .update(return_emailed_at=timezone.now())
        )
        return Response({'marked': updated}, status=status.HTTP_200_OK)