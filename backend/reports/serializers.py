from rest_framework import serializers

from shipments.serializers import ShipmentSerializer

from .models import DailyReport, DailyShipmentRecord


class DailyReportSerializer(serializers.ModelSerializer):
    """A report (draft or finalized). Read-only: changes go through the views below."""

    date = serializers.DateField(source='day.date')
    shipment_type = serializers.CharField(source='day.shipment_type')
    corrects_version = serializers.IntegerField(source='corrects.version', default=None)

    class Meta:
        model = DailyReport
        fields = [
            'id', 'date', 'shipment_type', 'version', 'corrects_version', 'correction_reason',
            'vans', 'bikes', 'third_party', 'reasons_text', 'notes', 'adjustments',
            'hub_name', 'calculated', 'figures', 'warnings',
            'is_finalized', 'finalized_at',
        ]


class AdjustmentSerializer(serializers.Serializer):
    value = serializers.IntegerField(min_value=0)
    note = serializers.CharField()


class ReportInputSerializer(serializers.Serializer):
    """
    What you can send to update a draft. Every field is optional:
    anything you leave out stays as it was.
    """

    vans = serializers.IntegerField(min_value=0, required=False)
    bikes = serializers.IntegerField(min_value=0, required=False)
    third_party = serializers.IntegerField(min_value=0, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    reasons_text = serializers.CharField(required=False, allow_blank=True)
    # {"delivered": {"value": 40, "note": "Counted at the gate"}}
    adjust = serializers.DictField(child=AdjustmentSerializer(), required=False)
    # ["delivered"] to remove an earlier override
    clear_adjust = serializers.ListField(child=serializers.CharField(), required=False)


class FinalizeSerializer(serializers.Serializer):
    accept_warnings = serializers.BooleanField(default=False)


class CorrectionSerializer(serializers.Serializer):
    reason = serializers.CharField()


class DayShipmentSerializer(serializers.ModelSerializer):
    """
    One shipment in a day's report: how it was counted (Inbound / Old Pending),
    how many days it has been at the hub, and its CURRENT details.
    """

    shipment = ShipmentSerializer(read_only=True)
    days_at_hub = serializers.SerializerMethodField()

    class Meta:
        model = DailyShipmentRecord
        fields = ['id', 'kind', 'days_at_hub', 'shipment']

    def get_days_at_hub(self, record):
        # 0 = first scanned on this day; 3 = first scanned three days earlier.
        return (record.day.date - record.shipment.first_seen_date).days