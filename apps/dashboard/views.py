from datetime import timedelta

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, F, Sum
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.facilities.models import Facility, FacilityMembership
from apps.inventory.models import InventoryAdjustment, InventoryItem, InventoryUpload
from apps.medicines.models import Medicine
from apps.prescriptions.models import DispenseEvent, Prescription, PrescriptionItem
from apps.search.models import SearchHistory


class HomeView(TemplateView):
    template_name = "home.html"


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/user_dashboard.html"

    def get_template_names(self):
        user = self.request.user
        if user.is_superuser or user.primary_role == User.Role.PLATFORM_ADMIN:
            return ["dashboard/platform_admin.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context.update({
            "dashboard_role": "Platform administrator" if user.is_superuser else user.get_primary_role_display(),
            "workspace_name": "My MedLocate",
            "metrics": [], "recent_rows": [], "quick_actions": [], "facilities": [],
        })
        if user.is_superuser or user.primary_role == User.Role.PLATFORM_ADMIN:
            self._platform_context(context)
        elif user.primary_role == User.Role.PATIENT:
            self._patient_context(context)
        elif user.primary_role == User.Role.DOCTOR:
            self._doctor_context(context)
        elif user.primary_role == User.Role.DISPENSER:
            self._dispenser_context(context)
        elif user.primary_role in {User.Role.INVENTORY, User.Role.FACILITY_ADMIN}:
            self._inventory_context(context)
        return context

    def _platform_context(self, context):
        now = timezone.now()
        today = timezone.localdate()
        inventory = InventoryItem.objects.select_related("facility", "medicine")
        context.update({
            "workspace_name": "Platform command centre",
            "dashboard_intro": "A live operational view of MedLocate access, facilities, stock and prescription activity.",
            "metrics": [
                {"label": "Registered users", "value": User.objects.count(), "note": f"{User.objects.filter(is_active=True).count()} active accounts"},
                {"label": "Active facilities", "value": Facility.objects.filter(status=Facility.Status.ACTIVE).count(), "note": f"{Facility.objects.count()} total facilities"},
                {"label": "Medicine catalogue", "value": Medicine.objects.filter(active=True).count(), "note": f"{inventory.count()} stock records"},
                {"label": "Open prescriptions", "value": Prescription.objects.filter(status__in=[Prescription.Status.ACTIVE, Prescription.Status.PARTIAL], valid_until__gt=now).count(), "note": "Active or partially dispensed"},
            ],
            "inventory_health": {
                "low": inventory.filter(quantity__lte=F("low_stock_threshold")).count(),
                "expired": inventory.filter(expiry_date__lt=today).count(),
                "stale": inventory.filter(updated_at__lt=now - timedelta(hours=settings.STOCK_STALE_HOURS)).count(),
                "zero": inventory.filter(quantity=0).count(),
            },
            "role_counts": [{"label": label, "count": User.objects.filter(primary_role=value).count()} for value, label in User.Role.choices],
            "facility_rows": Facility.objects.annotate(
                stock_records=Count("inventory", distinct=True), staff_count=Count("memberships", distinct=True), total_units=Sum("inventory__quantity"),
            ).order_by("name")[:8],
            "recent_audit": AuditEvent.objects.select_related("actor", "facility")[:8],
            "recent_users": User.objects.order_by("-date_joined")[:6],
            "quick_actions": [
                {"label": "Manage users", "detail": "Accounts and role access", "url": reverse("admin:accounts_user_changelist")},
                {"label": "Manage facilities", "detail": "Activation and locations", "url": reverse("admin:facilities_facility_changelist")},
                {"label": "Medicine catalogue", "detail": "Master medicine records", "url": reverse("admin:medicines_medicine_changelist")},
                {"label": "Audit evidence", "detail": "Append-only event history", "url": reverse("admin:audit_auditevent_changelist")},
            ],
        })

    def _patient_context(self, context):
        prescriptions = Prescription.objects.filter(patient=self.request.user).prefetch_related("items")
        active = prescriptions.filter(status__in=[Prescription.Status.ACTIVE, Prescription.Status.PARTIAL], valid_until__gt=timezone.now())
        recent_rows = []
        for prescription in prescriptions[:6]:
            recent_rows.append({
                "title": f"Prescription {str(prescription.uuid)[:8].upper()}",
                "meta": f"Issued {prescription.issued_at:%d %b %Y} · {prescription.items.count()} medicine item(s)",
                "status": prescription.get_status_display(), "status_class": prescription.status,
                "url": reverse("patient_prescription_detail", args=[prescription.pk]),
            })
        context.update({
            "dashboard_intro": "Find medicine, review prescriptions and return to recent activity from one place.",
            "metrics": [
                {"label": "Active prescriptions", "value": active.count(), "note": "Ready to present securely"},
                {"label": "All prescriptions", "value": prescriptions.count(), "note": "Your prescription history"},
                {"label": "Recent searches", "value": SearchHistory.objects.filter(patient=self.request.user).count(), "note": "Saved to this account"},
                {"label": "Items remaining", "value": PrescriptionItem.objects.filter(prescription__in=active).exclude(status=PrescriptionItem.Status.FULFILLED).count(), "note": "Across active prescriptions"},
            ],
            "recent_heading": "Recent prescriptions", "recent_rows": recent_rows,
            "quick_actions": [
                {"label": "Find medicine", "detail": "Search participating facilities", "url": reverse("medicine_search")},
                {"label": "My prescriptions", "detail": "Open QR prescriptions", "url": reverse("patient_prescription_list")},
            ],
        })

    def _doctor_context(self, context):
        prescriptions = Prescription.objects.filter(prescriber=self.request.user).select_related("patient").prefetch_related("items")
        recent_rows = [{
            "title": prescription.patient.get_full_name() or prescription.patient.username,
            "meta": f"Issued {prescription.issued_at:%d %b %Y} · {prescription.items.count()} item(s)",
            "status": prescription.get_status_display(), "status_class": prescription.status,
            "url": reverse("doctor_prescription_detail", args=[prescription.pk]),
        } for prescription in prescriptions[:7]]
        context.update({
            "dashboard_intro": "Create secure prescriptions and monitor fulfilment without exposing clinical details in QR codes.",
            "metrics": [
                {"label": "Issued prescriptions", "value": prescriptions.count(), "note": "All time"},
                {"label": "Currently active", "value": prescriptions.filter(status=Prescription.Status.ACTIVE, valid_until__gt=timezone.now()).count(), "note": "Within validity window"},
                {"label": "Partially dispensed", "value": prescriptions.filter(status=Prescription.Status.PARTIAL).count(), "note": "Requires follow-through"},
                {"label": "Patients served", "value": prescriptions.values("patient_id").distinct().count(), "note": "Unique patient accounts"},
            ],
            "recent_heading": "Recently issued", "recent_rows": recent_rows,
            "quick_actions": [
                {"label": "Create prescription", "detail": "Issue a secure expiring QR", "url": reverse("doctor_prescription_create")},
                {"label": "Issued prescriptions", "detail": "Review status and history", "url": reverse("doctor_prescription_list")},
            ],
        })

    def _member_facilities(self):
        return Facility.objects.filter(memberships__user=self.request.user, memberships__active=True).distinct()

    def _dispenser_context(self, context):
        facilities = self._member_facilities()
        events = DispenseEvent.objects.filter(facility__in=facilities).select_related("item__medicine", "facility", "dispensed_by").order_by("-timestamp")
        recent_rows = [{
            "title": event.item.medicine.name,
            "meta": f"{event.quantity} unit(s) · {event.facility.name} · {event.timestamp:%d %b, %H:%M}",
            "status": "Dispensed", "status_class": "dispensed", "url": "",
        } for event in events[:7]]
        context.update({
            "dashboard_intro": "Verify secure prescriptions, record fulfilment and protect facility stock.", "facilities": facilities,
            "metrics": [
                {"label": "Dispensed today", "value": events.filter(timestamp__date=timezone.localdate()).count(), "note": "At assigned facilities"},
                {"label": "My dispense events", "value": events.filter(dispensed_by=self.request.user).count(), "note": "Recorded by your account"},
                {"label": "Assigned facilities", "value": facilities.count(), "note": "Active memberships"},
                {"label": "Partial prescriptions", "value": Prescription.objects.filter(items__dispense_events__in=events, status=Prescription.Status.PARTIAL).distinct().count(), "note": "May require further supply"},
            ],
            "recent_heading": "Recent dispensing", "recent_rows": recent_rows,
            "quick_actions": [{"label": "Verify prescription", "detail": "Scan or enter a QR token", "url": reverse("dispense_scan")}],
        })

    def _inventory_context(self, context):
        facilities = self._member_facilities()
        items = InventoryItem.objects.filter(facility__in=facilities).select_related("medicine", "facility")
        now = timezone.now()
        adjustments = InventoryAdjustment.objects.filter(item__facility__in=facilities).select_related("item__medicine", "item__facility", "actor")
        recent_rows = [{
            "title": adjustment.item.medicine.name,
            "meta": f"{adjustment.previous_quantity} → {adjustment.new_quantity} · {adjustment.item.facility.name}",
            "status": adjustment.reason, "status_class": "updated",
            "url": reverse("inventory_edit", args=[adjustment.item.pk]),
        } for adjustment in adjustments.order_by("-created_at")[:7]]
        context.update({
            "dashboard_intro": "Keep participating-facility stock current, traceable and ready for patient search.", "facilities": facilities,
            "metrics": [
                {"label": "Stock records", "value": items.count(), "note": f"Across {facilities.count()} assigned facilities"},
                {"label": "Low stock", "value": items.filter(quantity__lte=F("low_stock_threshold")).count(), "note": "At or below threshold"},
                {"label": "Stale updates", "value": items.filter(updated_at__lt=now - timedelta(hours=settings.STOCK_STALE_HOURS)).count(), "note": "Needs confirmation"},
                {"label": "Expired batches", "value": items.filter(expiry_date__lt=timezone.localdate()).count(), "note": "Remove from availability"},
            ],
            "recent_heading": "Recent stock changes", "recent_rows": recent_rows,
            "recent_uploads": InventoryUpload.objects.filter(facility__in=facilities).select_related("facility", "uploaded_by")[:5],
            "quick_actions": [
                {"label": "Open inventory", "detail": "Review and update stock", "url": reverse("inventory_list")},
                {"label": "Import Excel", "detail": "Validate a stock workbook", "url": reverse("inventory_upload")},
                {"label": "Download template", "detail": "Use the approved format", "url": reverse("inventory_template")},
            ],
        })
        if self.request.user.primary_role == User.Role.FACILITY_ADMIN:
            context["metrics"][0]["note"] = f"{FacilityMembership.objects.filter(facility__in=facilities, active=True).count()} active staff memberships"
