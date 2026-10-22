from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin, UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from .models import PatientProfile, StaffProfile, User


@admin.register(User)
class MedLocateUserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    fieldsets = BaseUserAdmin.fieldsets + (("MedLocate", {"fields": ("primary_role",)}),)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (("MedLocate", {"fields": ("email", "primary_role")}),)
    list_display = ("username", "primary_role", "email", "is_active", "is_staff")
    list_filter = BaseUserAdmin.list_filter + ("primary_role",)


@admin.register(PatientProfile)
class PatientProfileAdmin(ModelAdmin):
    pass


@admin.register(StaffProfile)
class StaffProfileAdmin(ModelAdmin):
    pass


admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass
