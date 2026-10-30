from django.contrib import admin

from .models import Shipment, StatusHistory


class StatusHistoryInline(admin.TabularInline):
    """Shows a shipment's history at the bottom of its admin page (read-only)."""

    model = StatusHistory
    extra = 0
    can_delete = False
    readonly_fields = [
        'effective_date', 'old_status', 'new_status',
        'failure_reason', 'reason_note', 'note', 'changed_at',
    ]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ['waybill_number', 'status', 'failure_reason', 'first_seen_date', 'updated_at']
    list_filter = ['status', 'failure_reason']
    search_fields = ['waybill_number']
    inlines = [StatusHistoryInline]

    # Status fields can only change through the status service, which also
    # writes history. The admin is for viewing them, not editing them.
    readonly_fields = [
        'waybill_number', 'status', 'failure_reason', 'reason_note',
        'first_seen_date', 'created_at', 'updated_at',
    ]

    # New shipments come from the Excel import (or the service), never by hand here.
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StatusHistory)
class StatusHistoryAdmin(admin.ModelAdmin):
    list_display = ['shipment', 'old_status', 'new_status', 'effective_date', 'changed_at']
    list_filter = ['new_status', 'effective_date']
    search_fields = ['shipment__waybill_number']

    # History is append-only: viewable, never editable here.
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False