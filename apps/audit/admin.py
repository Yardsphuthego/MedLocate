from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(ModelAdmin):
    list_display = ("timestamp", "action", "actor", "object_type", "object_id", "facility")
    list_filter = ("action", "object_type")
    search_fields = ("actor__username", "action", "object_type", "object_id", "facility__name")
    list_select_related = ("actor", "facility")
    list_per_page = 30
    readonly_fields = ("actor", "action", "object_type", "object_id", "facility", "metadata", "timestamp")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
