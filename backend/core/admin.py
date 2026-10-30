from django.contrib import admin

from .models import FailureReason, HubConfig, StatusOption


@admin.register(HubConfig)
class HubConfigAdmin(admin.ModelAdmin):
    list_display = ['hub_name', 'reasons_format', 'updated_at']

    def has_add_permission(self, request):
        # Hide the "Add" button once the single config row exists.
        return not HubConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StatusOption)
class StatusOptionAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'requires_reason', 'sort_order', 'is_active']
    list_editable = ['sort_order', 'is_active']
    list_filter = ['category', 'is_active']


@admin.register(FailureReason)
class FailureReasonAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_other', 'sort_order', 'is_active']
    list_editable = ['sort_order', 'is_active']