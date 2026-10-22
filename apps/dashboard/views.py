from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from apps.accounts.access import CLINICAL_ROLES, require_staff, memberships
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Count, F, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView
from urllib.parse import urlsplit

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.facilities.models import Facility, FacilityMembership
from apps.inventory.models import InventoryAdjustment, InventoryItem, InventoryUpload
from apps.medicines.models import Medicine
from apps.prescriptions.models import DispenseEvent, Prescription, PrescriptionItem
from apps.search.models import SearchHistory


class HomeView(TemplateView):
    template_name = "home.html"


@login_required
def admin_workspace(request):
    if not request.user.is_staff:
        raise PermissionDenied
    target = request.GET.get("view", "/admin/")
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/admin/") or "\\" in target:
        raise Http404
    return render(request, "dashboard/admin_workspace.html", {"frame_url": target})


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
        if not (user.is_superuser or user.primary_role == User.Role.PLATFORM_ADMIN):
            require_staff(user, CLINICAL_ROLES)
        context.update({
            "dashboard_role": "Platform administrator" if user.is_superuser else user.get_primary_role_display(),
            "workspace_name": "My MedLocate",
            "updated_at": timezone.now(),
            "metrics": [], "recent_rows": [], "quick_actions": [], "facilities": [],
            "stock_preview": [], "focus_rows": [], "focus_heading": "", "focus_intro": "",
        })
        if user.is_superuser or user.primary_role == User.Role.PLATFORM_ADMIN:
            self._platform_context(context)
        elif user.primary_role == User.Role.DOCTOR:
            self._doctor_context(context)
        elif user.primary_role in {User.Role.NURSE, User.Role.DISPENSER}:
            self._dispenser_context(context)
        elif user.primary_role in {User.Role.PHARMACY, User.Role.INVENTORY, User.Role.FACILITY_ADMIN}:
            self._inventory_context(context)
        if user.primary_role in {User.Role.NURSE, User.Role.PHARMACY, User.Role.DISPENSER}:
            verified_today = AuditEvent.objects.filter(facility__in=self._member_facilities(), action="prescription.verified", timestamp__date=timezone.localdate()).count()
            if user.primary_role == User.Role.PHARMACY:
                context["shift_stats"] = [{"label": "Verified today", "value": verified_today}]
            else:
                context["metrics"].append({"label": "Verified today", "value": verified_today, "note": "At assigned facilities"})
        if user.primary_role in CLINICAL_ROLES:
            context["quick_actions"].append({"label": "History & reports", "detail": "Filter records for your role", "url": reverse("staff_reports")})
        if user.primary_role in {User.Role.DOCTOR, User.Role.NURSE}:
            context["quick_actions"].insert(0, {"label": "Find medicine", "detail": "Compare current stock and distance", "url": reverse("medicine_search")})
        if user.primary_role in {User.Role.DOCTOR, User.Role.NURSE, User.Role.PHARMACY}:
            context["quick_actions"].append({"label": "Identify medicine", "detail": "Scan and confirm a medicine barcode", "url": reverse("medicine_identify")})
        if user.primary_role == User.Role.PHARMACY:
            context["quick_actions"].append({"label": "Verify & dispense", "detail": "Record full or partial dispensing", "url": reverse("dispense_scan")})
            events = DispenseEvent.objects.filter(facility__in=self._member_facilities())
            context["shift_stats"].append({"label": "Dispensed today", "value": events.filter(timestamp__date=timezone.localdate()).count()})
        if user.primary_role in CLINICAL_ROLES:
            context["stock_preview"] = self._stock_preview(
                self._member_facilities() if user.primary_role in {User.Role.PHARMACY, User.Role.INVENTORY, User.Role.FACILITY_ADMIN, User.Role.DISPENSER} else None
            )
        return context

    def _stock_preview(self, facilities=None):
        items = InventoryItem.objects.filter(
            facility__status=Facility.Status.ACTIVE, medicine__active=True, quantity__gt=0,
        ).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=timezone.localdate()))
        if facilities is not None:
            items = items.filter(facility__in=facilities)
        return items.select_related("medicine", "facility").order_by("-updated_at", "pk")[:6]

    def _platform_context(self, context):
        now = timezone.now()
        today = timezone.localdate()
        inventory = InventoryItem.objects.select_related("facility", "medicine")
        query = self.request.GET.get("q", "").strip()[:160]
        status = self.request.GET.get("status", "")
        if status not in Facility.Status.values:
            status = ""
        facilities = Facility.objects.all()
        if query:
            facilities = facilities.filter(Q(name__icontains=query) | Q(address__icontains=query))
        if status:
            facilities = facilities.filter(status=status)
        # Keep stock sums independent from the membership join.
        stock_totals = (
            InventoryItem.objects.filter(facility=OuterRef("pk"))
            .order_by().values("facility").annotate(total=Sum("quantity")).values("total")
        )
        facilities = facilities.annotate(
            stock_records=Count("inventory", distinct=True),
            staff_count=Count(
                "memberships__user",
                filter=Q(memberships__active=True, memberships__user__is_active=True),
                distinct=True,
            ),
            total_units=Coalesce(Subquery(stock_totals), 0),
        ).order_by("name", "pk")
        facility_page = Paginator(facilities, 8).get_page(self.request.GET.get("page"))
        health_filters = {
            "low": ("Low-stock records", Q(quantity__lte=F("low_stock_threshold"))),
            "stale": ("Stale updates", Q(updated_at__lt=now - timedelta(hours=settings.STOCK_STALE_HOURS))),
            "expired": ("Expired batches", Q(expiry_date__lt=today)),
            "zero": ("Zero-stock records", Q(quantity=0)),
        }
        health = self.request.GET.get("health", "")
        if health not in health_filters:
            health = ""
        params = self.request.GET.copy()
        params.pop("page", None)
        health_params = params.copy()
        health_params.pop("health_page", None)
        health_params.pop("health", None)
        alerts = []
        for key, (label, condition) in health_filters.items():
            link_params = health_params.copy()
            link_params["health"] = key
            alerts.append({
                "key": key, "label": label, "count": inventory.filter(condition).count(),
                "url": "?" + link_params.urlencode() + "#inventory-review",
            })
        health_page = None
        if health:
            health_page = Paginator(
                inventory.filter(health_filters[health][1]).order_by("facility__name", "medicine__name", "pk"), 8,
            ).get_page(self.request.GET.get("health_page"))
        health_pagination = self.request.GET.copy()
        health_pagination.pop("health_page", None)
        can_admin = self.request.user.is_active and self.request.user.is_staff
        context.update({
            "can_admin": can_admin,
            "can_manage_facilities": can_admin and self.request.user.has_perm("facilities.view_facility"),
            "can_manage_users": can_admin and self.request.user.has_perm("accounts.view_user"),
            "can_view_audit": can_admin and self.request.user.has_perm("audit.view_auditevent"),
            "can_manage_inventory": can_admin and self.request.user.has_perm("inventory.view_inventoryitem"),
            "updated_at": now,
            "facility_query": query, "facility_status": status, "facility_statuses": Facility.Status.choices,
            "facility_page": facility_page, "facility_params": params.urlencode(),
            "health_alerts": alerts, "selected_health": health, "health_page": health_page,
            "health_heading": health_filters[health][0] if health else "",
            "health_params": health_pagination.urlencode(),
            "workspace_name": "Operations",
            "metrics": [
                {"label": "Active staff accounts", "value": User.objects.filter(is_active=True).filter(Q(is_superuser=True) | ~Q(primary_role=User.Role.PATIENT)).count(), "note": "Approved professional and admin users"},
                {"label": "Active facilities", "value": Facility.objects.filter(status=Facility.Status.ACTIVE).count(), "note": f"{Facility.objects.count()} total facilities"},
                {"label": "Medicine catalogue", "value": Medicine.objects.filter(active=True).count(), "note": f"{inventory.count()} stock records"},
                {"label": "Open prescriptions", "value": Prescription.objects.filter(status__in=[Prescription.Status.ACTIVE, Prescription.Status.PARTIAL], valid_until__gt=now).count(), "note": "Active or partially dispensed"},
            ],
            "facility_rows": facility_page,
            "recent_audit": AuditEvent.objects.select_related("actor", "facility")[:8],
            "recent_users": User.objects.filter(Q(is_superuser=True) | ~Q(primary_role=User.Role.PATIENT)).order_by("-date_joined")[:6],
        })
        controls = [
            ("accounts", "user", "Manage users", "Accounts and role access"),
            ("facilities", "facility", "Manage facilities", "Activation and locations"),
            ("facilities", "facilitymembership", "Staff memberships", "Facility assignments and access"),
            ("medicines", "medicine", "Medicine catalogue", "Master medicine records"),
            ("inventory", "inventoryitem", "Manage inventory", "Stock and batch records"),
            ("inventory", "inventoryupload", "Inventory imports", "Workbook processing history"),
            ("prescriptions", "prescription", "Prescriptions", "Prescription activity and status"),
            ("audit", "auditevent", "Audit evidence", "Append-only event history"),
        ]
        context["quick_actions"] = [
            {"label": label, "detail": detail, "url": reverse(f"admin:{app}_{model}_changelist")}
            for app, model, label, detail in controls
            if can_admin and self.request.user.has_perm(f"{app}.view_{model}")
        ]

        if self.request.user.is_superuser:
            context["quick_actions"].insert(0, {
                "label": "Create user", "detail": "Add an account and assign a role",
                "url": reverse("admin_user_create"),
            })

    def _doctor_context(self, context):
        prescriptions = Prescription.objects.filter(prescriber=self.request.user).select_related("patient").prefetch_related("items")
        recent_rows = [{
            "title": prescription.recipient_display,
            "meta": f"Issued {prescription.issued_at:%d %b %Y} · {prescription.items.count()} item(s)",
            "status": prescription.status_label, "status_class": prescription.effective_status,
            "url": reverse("doctor_prescription_detail", args=[prescription.pk]),
        } for prescription in prescriptions[:7]]
        context.update({
            "workspace_name": "Prescriptions",
            "dashboard_intro": "Issue QR prescriptions, follow their status and check current medicine availability.",
            "metrics": [
                {"label": "Issued", "value": prescriptions.count(), "note": "Prescriptions created"},
                {"label": "Open", "value": prescriptions.filter(status=Prescription.Status.ACTIVE, valid_until__gt=timezone.now()).count(), "note": "Within validity window"},
                {"label": "Partially dispensed", "value": prescriptions.filter(status=Prescription.Status.PARTIAL, valid_until__gt=timezone.now()).count(), "note": "Follow-up may be needed"},
            ],
            "recent_heading": "Recently issued", "recent_rows": recent_rows,
            "focus_heading": "Recent prescriptions",
            "focus_intro": "Your most recent prescriptions and their current status.",
            "focus_rows": recent_rows,
            "focus_url": reverse("doctor_prescription_list"),
            "focus_empty": "No prescriptions issued yet.",
            "primary_action": {"label": "Create prescription", "url": reverse("doctor_prescription_create")},
            "stock_heading": "Recorded stock",
            "stock_url": reverse("medicine_search"),
            "quick_actions": [
                {"label": "Create prescription", "detail": "Issue a secure expiring QR", "url": reverse("doctor_prescription_create")},
                {"label": "Issued prescriptions", "detail": "Review status and history", "url": reverse("doctor_prescription_list")},
            ],
        })

    def _member_facilities(self):
        return Facility.objects.filter(pk__in=memberships(self.request.user, CLINICAL_ROLES).values("facility_id"))

    def _dispenser_context(self, context):
        facilities = self._member_facilities()
        events = DispenseEvent.objects.filter(facility__in=facilities).select_related("item__medicine", "facility", "dispensed_by").order_by("-timestamp")
        recent_rows = [{
            "title": event.item.medicine.name,
            "meta": f"{event.quantity} unit(s) · {event.facility.name} · {event.timestamp:%d %b, %H:%M}",
            "status": "Dispensed", "status_class": "dispensed", "url": "",
        } for event in events[:7]]
        context.update({
            "workspace_name": "Dispensing",
            "dashboard_intro": "Verify QR references and record dispensing at your assigned facilities.", "facilities": facilities,
            "metrics": [
                {"label": "Dispensed today", "value": events.filter(timestamp__date=timezone.localdate()).count(), "note": "At assigned facilities"},
                {"label": "My dispense events", "value": events.filter(dispensed_by=self.request.user).count(), "note": "Recorded by your account"},
                {"label": "Assigned facilities", "value": facilities.count(), "note": "Active memberships"},
            ],
            "recent_heading": "Recent dispensing", "recent_rows": recent_rows,
            "focus_heading": "Recent dispensing",
            "focus_intro": "Confirmed transactions at your assigned facilities.",
            "focus_rows": recent_rows,
            "focus_url": reverse("staff_reports"),
            "focus_empty": "No dispensing recorded at your assigned facilities yet.",
            "primary_action": {"label": "Verify prescription", "url": reverse("dispense_scan")},
            "stock_heading": "Recorded stock",
            "stock_url": reverse("medicine_search") if self.request.user.primary_role == User.Role.NURSE else "",
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
        attention = items.filter(
            Q(quantity__lte=F("low_stock_threshold")) |
            Q(updated_at__lt=now - timedelta(hours=settings.STOCK_STALE_HOURS)) |
            Q(expiry_date__lte=timezone.localdate() + timedelta(days=30))
        ).order_by("expiry_date", "quantity", "updated_at", "pk")[:8]
        attention_rows = []
        for item in attention:
            if item.is_expired:
                status, status_class = "Expired", "expired"
            elif item.quantity == 0:
                status, status_class = "Out of stock", "zero"
            elif item.quantity <= item.low_stock_threshold:
                status, status_class = "Low stock", "low"
            elif item.expiry_date and item.expiry_date <= timezone.localdate() + timedelta(days=30):
                status, status_class = "Expiring soon", "aging"
            else:
                status, status_class = "Update needed", "stale"
            attention_rows.append({
                "title": item.medicine.name,
                "meta": f"{item.facility.name} · {item.quantity} units · updated {item.updated_at:%d %b}",
                "status": status, "status_class": status_class,
                "url": reverse("inventory_edit", args=[item.pk]),
            })
        context.update({
            "workspace_name": "Inventory",
            "dashboard_intro": "Review stock that needs attention and maintain current facility records.", "facilities": facilities,
            "metrics": [
                {"label": "Stock records", "value": items.count(), "note": f"Across {facilities.count()} assigned facilities"},
                {"label": "Low stock", "value": items.filter(quantity__lte=F("low_stock_threshold")).count(), "note": "At or below threshold"},
                {"label": "Out of stock", "value": items.filter(quantity=0).count(), "note": "Zero units recorded"},
                {"label": "Expiring within 30 days", "value": items.filter(expiry_date__range=(timezone.localdate(), timezone.localdate() + timedelta(days=30))).count(), "note": "Review batches"},
            ],
            "recent_heading": "Recent stock changes", "recent_rows": recent_rows,
            "show_activity_panel": True,
            "focus_heading": "Stock requiring review",
            "focus_intro": "Low, stale or expiring records at your facilities.",
            "focus_rows": attention_rows,
            "focus_url": reverse("inventory_list"),
            "focus_empty": "No stock records need review right now.",
            "primary_action": {"label": "Open inventory", "url": reverse("inventory_list")},
            "stock_heading": "Recently updated stock",
            "stock_url": reverse("inventory_list"),
            "recent_uploads": InventoryUpload.objects.filter(facility__in=facilities).select_related("facility", "uploaded_by")[:5],
            "quick_actions": [
                {"label": "Open inventory", "detail": "Review and update stock", "url": reverse("inventory_list")},
                {"label": "Import Excel", "detail": "Validate a stock workbook", "url": reverse("inventory_upload")},
                {"label": "Download template", "detail": "Use the approved format", "url": reverse("inventory_template")},
            ],
        })
        if self.request.user.primary_role == User.Role.FACILITY_ADMIN:
            context["metrics"][0]["note"] = f"{FacilityMembership.objects.filter(facility__in=facilities, active=True).count()} active staff memberships"
