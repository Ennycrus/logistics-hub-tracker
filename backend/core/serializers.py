from rest_framework import serializers

from .models import FailureReason, HubConfig, StatusOption


# --- Dropdown options (used by the Shipments page) -------------------------

class StatusOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatusOption
        fields = ['id', 'name', 'category', 'requires_reason', 'sort_order']


class FailureReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = FailureReason
        fields = ['id', 'name', 'is_other', 'sort_order']


# --- Settings page ---------------------------------------------------------

class HubConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = HubConfig
        fields = ['hub_name', 'reasons_format', 'updated_at']
        read_only_fields = ['updated_at']

    def validate_hub_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Hub name cannot be empty.')
        return value


def status_in_use(status):
    """True if any shipment or history row uses this status."""
    from shipments.models import Shipment, StatusHistory  # imported here to avoid a circular import
    return (
        Shipment.objects.filter(status=status).exists()
        or StatusHistory.objects.filter(new_status=status).exists()
        or StatusHistory.objects.filter(old_status=status).exists()
    )


class StatusSettingsSerializer(serializers.ModelSerializer):
    """
    Create and edit statuses. Rules that protect your records:
      - A status that has been used keeps its category and "requires reason"
        setting, because past figures and history depend on them.
        You can still rename it, reorder it or switch it off.
      - The last active "not yet checked" status can't be switched off,
        because every imported shipment starts with it.
      - Statuses are never deleted, only switched off.
    """

    in_use = serializers.SerializerMethodField()

    class Meta:
        model = StatusOption
        fields = ['id', 'name', 'category', 'requires_reason', 'sort_order', 'is_active', 'in_use']

    def get_in_use(self, obj):
        return status_in_use(obj)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Name cannot be empty.')
        return value

    def validate(self, attrs):
        status = self.instance
        if status is None:
            return attrs  # creating a new status: nothing to protect yet

        if status_in_use(status):
            for field, label in [('category', 'category'), ('requires_reason', '"requires reason" setting')]:
                if field in attrs and attrs[field] != getattr(status, field):
                    raise serializers.ValidationError(
                        {field: f'This status is already used, so its {label} cannot change. '
                                f'Create a new status instead.'}
                    )

        switching_off = attrs.get('is_active') is False and status.is_active
        if switching_off and status.category == StatusOption.CATEGORY_UNCHECKED:
            others = StatusOption.objects.filter(
                category=StatusOption.CATEGORY_UNCHECKED, is_active=True,
            ).exclude(pk=status.pk)
            if not others.exists():
                raise serializers.ValidationError(
                    {'is_active': 'You need at least one active "not yet checked" status for imports.'}
                )
        return attrs


class ReasonSettingsSerializer(serializers.ModelSerializer):
    """Create and edit failure reasons. Reasons are never deleted, only switched off."""

    class Meta:
        model = FailureReason
        fields = ['id', 'name', 'is_other', 'sort_order', 'is_active']

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Name cannot be empty.')
        return value