from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import InventoryAdjustment, InventoryItem, InventoryUpload, InventoryUploadRow


@admin.register(InventoryItem)
class InventoryItemAdmin(ModelAdmin):
    list_display = ("medicine", "quantity", "facility", "expiry_date", "batch_number", "updated_at")
    list_filter = ("facility", "expiry_date")
    search_fields = ("medicine__name", "medicine__code", "facility__name", "batch_number")
    list_select_related = ("medicine", "facility")
    list_per_page = 30


@admin.register(InventoryAdjustment)
class InventoryAdjustmentAdmin(ModelAdmin):
    list_display = ("item", "previous_quantity", "new_quantity", "reason", "actor", "created_at")
    list_filter = ("created_at",)
    search_fields = ("item__medicine__name", "item__facility__name", "reason", "actor__username")
    list_select_related = ("item__medicine", "item__facility", "actor")
    list_per_page = 30


@admin.register(InventoryUpload)
class InventoryUploadAdmin(ModelAdmin):
    list_display = ("original_name", "facility", "status", "accepted_count", "rejected_count", "uploaded_by", "created_at")
    list_filter = ("status", "facility")
    search_fields = ("original_name", "file_hash", "facility__name")
    list_select_related = ("facility", "uploaded_by")
    list_per_page = 30


@admin.register(InventoryUploadRow)
class InventoryUploadRowAdmin(ModelAdmin):
    list_display = ("upload", "row_number", "status", "error_text")
    list_filter = ("status",)
    search_fields = ("upload__original_name", "error_text")
    list_select_related = ("upload",)
    list_per_page = 30
