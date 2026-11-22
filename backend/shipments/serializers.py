from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from core.models import FailureReason, StatusOption

from .models import DELIVERED_BY_CHOICES, ImportBatch, ImportRow, Shipment, StatusHistory
from .services.attempts import failed_attempts, is_ready_for_return


class StatusHistorySerializer(serializers.ModelSerializer):
    old_status = serializers.CharField(source='old_status.name', default=None)
    new_status = serializers.CharField(source='new_status.name')
    failure_reason = serializers.CharField(source='failure_reason.name', default=None)

    class Meta:
        model = StatusHistory
        fields = [
            'id', 'old_status', 'new_status', 'failure_reason',
            'reason_note', 'delivered_by', 'note', 'effective_date', 'changed_at',
        ]


class ShipmentSerializer(serializers.ModelSerializer):
    """One row of the shipments table. Read-only: status changes use the endpoint below."""

    status_name = serializers.CharField(source='status.name')
    status_category = serializers.CharField(source='status.category')
    failure_reason_name = serializers.CharField(source='failure_reason.name', default=None)
    # How many times this shipment has been Delivery Unsuccessful, whether that
    # has reached the point where the hub should initiate a return, and the date
    # of its most recent status change (see services/attempts.py).
    attempt_count = serializers.SerializerMethodField()
    ready_for_return = serializers.SerializerMethodField()
    last_update = serializers.SerializerMethodField()

    def get_attempt_count(self, obj):
        count = getattr(obj, 'attempt_count', None)  # set by with_attempt_count() on list/detail
        return failed_attempts(obj) if count is None else count

    def get_ready_for_return(self, obj):
        return is_ready_for_return(self.get_attempt_count(obj), obj.status.category)

    def get_last_update(self, obj):
        # The date of the most recent status change (used to allow a repeat attempt
        # only on a later day). Annotated on list/detail; computed otherwise.
        value = getattr(obj, 'last_update', None)
        if value is None:
            value = (
                obj.history.order_by('-effective_date', '-changed_at', '-pk')
                .values_list('effective_date', flat=True).first()
            )
        return value.isoformat() if value else None

    class Meta:
        model = Shipment
        fields = [
            'id', 'waybill_number', 'shipment_type',
            'status', 'status_name', 'status_category',
            'failure_reason', 'failure_reason_name', 'reason_note', 'delivered_by',
            'notes', 'first_seen_date', 'updated_at',
            'attempt_count', 'ready_for_return', 'last_update',
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
    # Who delivered it: rider, captain or 3pl (only used for a delivered status).
    delivered_by = serializers.ChoiceField(
        choices=DELIVERED_BY_CHOICES, required=False, allow_blank=True, default='',
    )
    note = serializers.CharField(required=False, allow_blank=True, default='')
    effective_date = serializers.DateField(required=False)
    # True = "I know that day's report is already finalized, save anyway".
    allow_finalized_day = serializers.BooleanField(required=False, default=False)

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
    column = serializers.IntegerField(required=False, min_value=0); all_columns = serializers.BooleanField(required=False, default=False)

    def validate_file(self, file):
        if not file.name.lower().endswith(('.xlsx', '.csv', '.txt')):
            raise serializers.ValidationError('Please upload an Excel .xlsx file (or paste the list).')
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
            'new_count', 'base_new_count', 'temu_new_count', 'duplicate_in_file_count', 'existing_outstanding_count',
            'existing_closed_count', 'invalid_count', 'imported_at',
        ]


class ImportBatchDetailSerializer(ImportBatchSerializer):
    rows = ImportRowSerializer(many=True, read_only=True)

    class Meta(ImportBatchSerializer.Meta):
        fields = ImportBatchSerializer.Meta.fields + ['rows']