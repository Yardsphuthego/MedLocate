from django.contrib import admin
from .models import Medicine, MedicineAlias


class AliasInline(admin.TabularInline):
    model = MedicineAlias
    extra = 1


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "strength", "form", "active")
    list_filter = ("active", "form")
    search_fields = ("code", "name", "generic_name", "aliases__name")
    inlines = [AliasInline]
