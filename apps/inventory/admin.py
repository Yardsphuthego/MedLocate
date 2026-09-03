from django.contrib import admin
from .models import InventoryAdjustment, InventoryItem, InventoryUpload, InventoryUploadRow

admin.site.register(InventoryItem)
admin.site.register(InventoryAdjustment)
admin.site.register(InventoryUpload)
admin.site.register(InventoryUploadRow)
