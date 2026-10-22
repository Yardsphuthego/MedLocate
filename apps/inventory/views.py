from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from openpyxl import Workbook

from apps.accounts.models import User
from apps.facilities.models import FacilityMembership
from .forms import InventoryItemForm, InventoryUploadForm
from .models import InventoryItem, InventoryUpload
from .services import commit_inventory_upload, save_inventory_item, validate_inventory_workbook

from apps.accounts.access import INVENTORY_ROLES, require_membership

ALLOWED_ROLES = INVENTORY_ROLES


def active_membership(request):
    return require_membership(request.user, INVENTORY_ROLES, request.session.get("active_facility"))


def inventory_list(request):
    membership = active_membership(request)
    facility = membership.facility
    items = InventoryItem.objects.filter(facility=facility).select_related("medicine")
    query = request.GET.get("q", "").strip()
    if query:
        items = items.filter(Q(medicine__name__icontains=query) | Q(medicine__code__icontains=query))
    return render(request, "inventory/list.html", {"facility": facility, "items": items, "query": query})


def inventory_edit(request, pk=None):
    membership = active_membership(request)
    facility = membership.facility
    item = get_object_or_404(InventoryItem, pk=pk, facility=facility) if pk else None
    form = InventoryItemForm(request.POST or None, instance=item, facility=facility)
    if request.method == "POST" and form.is_valid():
        save_inventory_item(form=form, facility=facility, actor=request.user)
        messages.success(request, "Stock record saved and audited.")
        return redirect("inventory_list")
    return render(request, "inventory/form.html", {"form": form, "item": item, "facility": facility})


def inventory_upload(request):
    membership = active_membership(request)
    form = InventoryUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        upload = validate_inventory_workbook(
            uploaded_file=form.cleaned_data["workbook"], facility=membership.facility, actor=request.user
        )
        return redirect("inventory_upload_preview", pk=upload.pk)
    history = InventoryUpload.objects.filter(facility=membership.facility).select_related("uploaded_by")[:10]
    return render(request, "inventory/upload.html", {"form": form, "facility": membership.facility, "history": history})


def inventory_upload_preview(request, pk):
    membership = active_membership(request)
    upload = get_object_or_404(InventoryUpload, pk=pk, facility=membership.facility)
    if request.method == "POST":
        try:
            changed = commit_inventory_upload(upload=upload, actor=request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Imported {changed} stock records as a snapshot.")
            return redirect("inventory_list")
        upload.refresh_from_db()
    return render(request, "inventory/upload_preview.html", {"upload": upload, "facility": membership.facility})


def inventory_template(request):
    active_membership(request)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "inventory"
    sheet.append(["medicine_code", "medicine_name", "strength", "form", "quantity", "expiry_date", "last_updated", "batch_number"])
    sheet.append(["MED-PAR-500", "Paracetamol", "500 mg", "tablet", 25, "2027-12-31", "", "BATCH-001"])
    output = __import__("io").BytesIO()
    workbook.save(output)
    response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="medlocate_inventory_template.xlsx"'
    return response
