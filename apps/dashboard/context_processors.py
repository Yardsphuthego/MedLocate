from django.contrib import admin
from django.urls import reverse

from apps.accounts.models import User


WORKSPACE_PREFIXES = (
    "/dashboard/", "/clinical/", "/facility/inventory/",
    "/doctor/prescriptions/", "/dispense/", "/accounts/users/new/", "/admin/",
)


def workspace_context(request):
    user = request.user
    if not user.is_authenticated or not user.is_active or not request.path.startswith(WORKSPACE_PREFIXES):
        return {}

    role = user.primary_role
    actions = []
    if user.is_superuser or role == User.Role.PLATFORM_ADMIN:
        for app, model, label in (
            ("accounts", "user", "Users"),
            ("facilities", "facility", "Facilities"),
            ("facilities", "facilitymembership", "Staff"),
            ("medicines", "medicine", "Medicines"),
            ("inventory", "inventoryitem", "Inventory"),
            ("inventory", "inventoryupload", "Imports"),
            ("prescriptions", "prescription", "Prescriptions"),
            ("audit", "auditevent", "Audit"),
        ):
            if user.has_perm(f"{app}.view_{model}"):
                actions.append({"label": label, "url": reverse(f"admin:{app}_{model}_changelist")})
    else:
        if role in {User.Role.DOCTOR, User.Role.NURSE}:
            actions.append({"label": "Find medicine", "url": reverse("medicine_search")})
        if role == User.Role.DOCTOR:
            actions.extend([
                {"label": "New prescription", "url": reverse("doctor_prescription_create")},
                {"label": "Issued prescriptions", "url": reverse("doctor_prescription_list")},
            ])
        if role in {User.Role.PHARMACY, User.Role.INVENTORY, User.Role.FACILITY_ADMIN}:
            actions.extend([
                {"label": "Inventory", "url": reverse("inventory_list")},
                {"label": "Import Excel", "url": reverse("inventory_upload")},
            ])
        if role in {User.Role.NURSE, User.Role.PHARMACY, User.Role.DISPENSER}:
            actions.append({"label": "Verify & dispense", "url": reverse("dispense_scan")})
        actions.append({"label": "Reports", "url": reverse("staff_reports")})
        if role in {User.Role.DOCTOR, User.Role.NURSE, User.Role.PHARMACY}:
            actions.append({"label": "Identify medicine", "url": reverse("medicine_identify")})

    current = request.GET.get("view", request.path)
    for action in actions:
        action["active"] = current.startswith(action["url"])

    return {
        **({} if request.path.startswith("/admin/") else admin.site.each_context(request)),
        "dashboard_role": "Platform administrator" if user.is_superuser else user.get_primary_role_display(),
        "workspace_name": "MedLocate workspace",
        "quick_actions": actions,
        "workspace_tabs": actions,
    }
