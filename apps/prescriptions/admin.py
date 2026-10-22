from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from .models import DispenseEvent, Prescription, PrescriptionItem


class PrescriptionItemInline(TabularInline):
    model = PrescriptionItem
    extra = 0
    readonly_fields = ("dispensed_quantity", "status")


@admin.register(Prescription)
class PrescriptionAdmin(ModelAdmin):
    list_display = ("uuid", "status", "recipient", "issuing_facility", "prescriber", "issued_at", "valid_until")
    list_filter = ("status", "issuing_facility")
    search_fields = ("recipient_name", "recipient_reference", "prescriber__username", "uuid")
    list_select_related = ("prescriber", "patient", "issuing_facility")
    list_per_page = 30
    readonly_fields = ("uuid", "token_hash", "token_hint", "qr_image", "issued_at")
    inlines = [PrescriptionItemInline]

    @admin.display(description="Recipient")
    def recipient(self, obj):
        return obj.recipient_display


@admin.register(DispenseEvent)
class DispenseEventAdmin(ModelAdmin):
    list_display = ("item", "facility", "quantity", "dispensed_by", "timestamp")
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
