from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Facility, FacilityMembership


@admin.register(Facility)
class FacilityAdmin(ModelAdmin):
    list_display = ("name", "status", "facility_type", "address", "phone")
    list_filter = ("status", "facility_type")
    search_fields = ("name", "address", "phone")
    ordering = ("name",)
    list_per_page = 30


@admin.register(FacilityMembership)
class FacilityMembershipAdmin(ModelAdmin):
    list_display = ("user", "facility", "role", "active")
    list_filter = ("role", "active")
    search_fields = ("user__username", "user__email", "facility__name")
    list_select_related = ("user", "facility")
    list_per_page = 30
