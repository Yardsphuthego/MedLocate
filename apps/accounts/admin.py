from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import PatientProfile, StaffProfile, User


@admin.register(User)
class MedLocateUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("MedLocate", {"fields": ("primary_role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("MedLocate", {"fields": ("email", "primary_role")}),)
    list_display = ("username", "email", "primary_role", "is_active", "is_staff")
    list_filter = UserAdmin.list_filter + ("primary_role",)


admin.site.register(PatientProfile)
admin.site.register(StaffProfile)
