from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from .models import Medicine, MedicineAlias


class AliasInline(TabularInline):
    model = MedicineAlias
    extra = 1


@admin.register(Medicine)
class MedicineAdmin(ModelAdmin):
    list_display = ("code", "name", "generic_name", "strength", "form", "active")
    list_filter = ("active", "form")
    search_fields = ("code", "name", "generic_name", "aliases__name")
    inlines = [AliasInline]
