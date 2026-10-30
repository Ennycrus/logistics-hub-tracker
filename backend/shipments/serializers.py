from django.utils import timezone
from rest_framework import serializers

from core.models import FailureReason, StatusOption

from .models import ImportBatch, ImportRow, Shipment, StatusHistory


class StatusHistorySerializer(serializers.ModelSerializer):
    old_status = serializers.CharField(source='old_status.name', default=None)
    new_status = serializers.CharField(source='new_status.name')
    failure_reason = serializers.CharField(source='failure_reason.name', default=None)

    class Meta:
        model = StatusHistory
        fields = [
            'id', 'old_status', 'new_status', 'failure_reason',
            'reason_note', 'note', 'effective_date', 'changed_at',
        ]


class ShipmentSerializer(serializers.ModelSerializer):
    """One row of the shipments table. Read-only: status changes use the endpoint below."""

    status_name = serializers.CharField(source='status.name')
    status_category = serializers.CharField(source='status.category')
    failure_reason_name = serializers.CharField(source='failure_reason.name', default=None)

    class Meta:
        model = Shipment
        fields = [
            'id', 'waybill_number', 'shipment_type',
            'status', 'status_name', 'status_category',
            'failure_reason', 'failure_reason_name', 'reason_note',
            'notes', 'first_seen_date', 'updated_at',
        ]


class ShipmentDetailSerializer(ShipmentSerializer):
    """A single shipment, including its full history."""

    history = StatusHistorySerializer(many=True, read_only=True)

    class Meta(ShipmentSerializer.Meta):
        fields = ShipmentSerializer.Meta.fields + ['history']


class StatusChangeSerializer(serializers.Serializer):
    """
    Checks the INPUT shape for a status change (right types, ids that exist).
    The business rules (reason required, "Other" needs a note...) stay in
    the status service, so they apply everywhere, not only in the API.
    """

    status = serializers.PrimaryKeyRelatedField(queryset=StatusOption.objects.all())
    failure_reason = serializers.PrimaryKeyRelatedField(
        queryset=FailureReason.objects.filter(is_active=True), required=False, allow_null=True,
    )
    reason_note = serializers.CharField(required=False, allow_blank=True, default='')
    note = serializers.CharField(required=False, allow_blank=True, default='')
    effective_date = serializers.DateField(required=False)

    def validate_effective_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError('The date cannot be in the future.')
        return value


class NotesSerializer(serializers.Serializer):
    """Your own notes on a shipment. Plain text, not part of the report."""

    notes = serializers.CharField(allow_blank=True, max_length=1000, trim_whitespace=True)


class BulkStatusChangeSerializer(StatusChangeSerializer):
    """The same fields as a single change, plus the list of shipments."""

    shipment_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=500,
    )


# --- Imports ---------------------------------------------------------------

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB is far more than any scanner file needs


class ImportUploadSerializer(serializers.Serializer):
    """The file (and optional column choice) sent for a preview."""

    file = serializers.FileField()
    column = serializers.IntegerField(required=False, min_value=0)

    def validate_file(self, file):
        if not file.name.lower().endswith('.xlsx'):
            raise serializers.ValidationError('Please upload an Excel .xlsx file.')
        if file.size > MAX_UPLOAD_BYTES:
            raise serializers.ValidationError('The file is too large (max 5 MB).')
        return file


class ImportConfirmSerializer(ImportUploadSerializer):
    """A confirm also needs the reporting date the file belongs to."""

    reporting_date = serializers.DateField()
    # What to do with new waybills that start with neither 1 nor 3034.
    unknown_type = serializers.ChoiceField(
        choices=['base', 'temu', 'skip'], required=False, allow_blank=True,
    )

    def validate_reporting_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError('The date cannot be in the future.')
        return value


class ImportRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRow
        fields = ['row_number', 'waybill_number', 'result', 'message']


class ImportBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportBatch
        fields = [
            'id', 'file_name', 'reporting_date', 'column_index', 'total_rows',
            'new_count', 'base_new_count', 'temu_new_count', 'duplicate_in_file_count',
            'existing_outstanding_count', 'existing_closed_count', 'invalid_count', 'imported_at',
        ]


class ImportBatchDetailSerializer(ImportBatchSerializer):
    rows = ImportRowSerializer(many=True, read_only=True)

    class Meta(ImportBatchSerializer.Meta):
        fields = ImportBatchSerializer.Meta.fields + ['rows']