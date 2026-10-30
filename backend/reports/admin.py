from django.contrib import admin

from .models import DailyReport, DailyShipmentRecord, ReportingDay


class DailyShipmentRecordInline(admin.TabularInline):
    model = DailyShipmentRecord
    extra = 0
    can_delete = False
    fields = ['shipment', 'kind']
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ReportingDay)
class ReportingDayAdmin(admin.ModelAdmin):
    list_display = ['date', 'state', 'inbound_count', 'old_pending_count', 'updated_at']
    readonly_fields = ['date', 'state', 'created_at', 'updated_at']
    inlines = [DailyShipmentRecordInline]

    def inbound_count(self, obj):
        return obj.records.filter(kind=DailyShipmentRecord.KIND_INBOUND).count()

    def old_pending_count(self, obj):
        return obj.records.filter(kind=DailyShipmentRecord.KIND_OLD_PENDING).count()

    # Days are created and refreshed only by the day service.
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DailyShipmentRecord)
class DailyShipmentRecordAdmin(admin.ModelAdmin):
    list_display = ['day', 'shipment', 'kind']
    list_filter = ['kind', 'day']
    search_fields = ['shipment__waybill_number']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DailyReport)
class DailyReportAdmin(admin.ModelAdmin):
    list_display = ['day', 'version', 'is_finalized', 'vans', 'bikes', 'third_party', 'finalized_at']
    list_filter = ['is_finalized']

    # Reports are created, finalized and corrected only through the report service.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False