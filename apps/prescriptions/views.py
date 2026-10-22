import uuid
from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from apps.accounts.decorators import roles_required
from apps.accounts.models import User
from apps.accounts.access import DISPENSE_ROLES, require_staff, require_membership
from apps.audit.services import record_event
from apps.facilities.models import FacilityMembership
from .forms import DispenseForm, PrescriptionForm, PrescriptionItemFormSet, TokenScanForm
from .models import Prescription
from .services import DispenseError, cancel_prescription, create_prescription, dispense_prescription, prescription_for_token


def _active_staff(user, role):
    require_staff(user, {role})


def _dispenser_membership(request):
    return require_membership(request.user, DISPENSE_ROLES, request.session.get("active_facility"))


@roles_required(User.Role.DOCTOR)
def doctor_prescription_list(request):
    _active_staff(request.user, User.Role.DOCTOR)
    prescriptions = Prescription.objects.filter(prescriber=request.user).select_related("patient").prefetch_related("items")
    return render(request, "prescriptions/doctor_list.html", {"prescriptions": prescriptions})


@roles_required(User.Role.DOCTOR)
def doctor_prescription_create(request):
    _active_staff(request.user, User.Role.DOCTOR)
    initial_expiry = timezone.localtime() + timedelta(hours=settings.PRESCRIPTION_DEFAULT_VALIDITY_HOURS)
    form = PrescriptionForm(request.POST or None, initial={"valid_until": initial_expiry.strftime("%Y-%m-%dT%H:%M")})
    formset = PrescriptionItemFormSet(request.POST or None, prefix="items")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        try:
            prescription = create_prescription(form=form, item_formset=formset, prescriber=request.user, facility_id=request.session.get("active_facility"))
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Prescription created. Print the QR reference for the recipient.")
            return redirect("doctor_prescription_detail", pk=prescription.pk)
    return render(request, "prescriptions/create.html", {"form": form, "formset": formset})


@roles_required(User.Role.DOCTOR)
def doctor_prescription_detail(request, pk):
    _active_staff(request.user, User.Role.DOCTOR)
    prescription = get_object_or_404(Prescription.objects.prefetch_related("items__medicine"), pk=pk, prescriber=request.user)
    return render(request, "prescriptions/detail.html", {"prescription": prescription, "viewer": "doctor"})


@roles_required(User.Role.DOCTOR)
def doctor_prescription_cancel(request, pk):
    _active_staff(request.user, User.Role.DOCTOR)
    prescription = get_object_or_404(Prescription, pk=pk, prescriber=request.user)
    if request.method != "POST":
        return render(request, "prescriptions/cancel.html", {"prescription": prescription})
    try:
        cancel_prescription(prescription=prescription, actor=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Prescription cancelled. It can no longer be dispensed.")
    return redirect("doctor_prescription_detail", pk=prescription.pk)


def prescription_qr(request, pk):
    if not request.user.is_authenticated:
        raise PermissionDenied
    prescription = get_object_or_404(Prescription, pk=pk)
    _active_staff(request.user, User.Role.DOCTOR)
    if prescription.prescriber_id != request.user.pk:
        raise PermissionDenied
    return FileResponse(prescription.qr_image.open("rb"), content_type="image/png")


@roles_required(*DISPENSE_ROLES)
def dispense_scan(request):
    membership = _dispenser_membership(request)
    form = TokenScanForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        return redirect("dispense_verify", token=form.cleaned_data["token"])
    return render(request, "dispensing/scan.html", {"form": form, "facility": membership.facility})


@roles_required(*DISPENSE_ROLES)
def dispense_verify(request, token):
    membership = _dispenser_membership(request)
    prescription = prescription_for_token(token)
    if prescription is None:
        record_event(actor=request.user, action="verification.rejected", facility=membership.facility)
        return render(request, "dispensing/invalid.html", status=404)
    if not prescription.is_usable:
        record_event(actor=request.user, action="verification.rejected", obj=prescription, facility=membership.facility)
        return render(request, "dispensing/invalid.html", {"reason": f"Prescription is {prescription.status_label.lower()}."}, status=409)
    items = list(prescription.items.select_related("medicine"))
    form = DispenseForm(request.POST or None, items=items, initial={"confirmation_key": uuid.uuid4()})
    if request.method == "GET" and prescription.is_usable:
        record_event(actor=request.user, action="prescription.verified", obj=prescription, facility=membership.facility)
    if request.method == "POST" and form.is_valid():
        try:
            dispense_prescription(
                prescription=prescription, quantities=form.quantities(),
                facility=membership.facility, dispenser=request.user, confirmation_key=form.cleaned_data["confirmation_key"],
            )
        except DispenseError as exc:
            record_event(actor=request.user, action="dispensing.rejected", obj=prescription, facility=membership.facility)
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Dispensing recorded and facility stock updated atomically.")
            return redirect("staff_reports")
    prescription.refresh_from_db()
    return render(request, "dispensing/verify.html", {
        "prescription": prescription, "items": items, "form": form, "facility": membership.facility,
    })
