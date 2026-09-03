from django.contrib import admin
from .models import DispenseEvent, Prescription, PrescriptionItem


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 0
    readonly_fields = ("dispensed_quantity", "status")


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("uuid", "patient", "prescriber", "status", "issued_at", "valid_until")
    list_filter = ("status",)
    readonly_fields = ("uuid", "token_hash", "token_hint", "qr_image", "issued_at")
    inlines = [PrescriptionItemInline]


admin.site.register(DispenseEvent)
