from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from apps.accounts.decorators import roles_required
from apps.accounts.models import User
from apps.facilities.models import FacilityMembership
from .forms import DispenseForm, PrescriptionForm, PrescriptionItemFormSet, TokenScanForm
from .models import Prescription
from .services import DispenseError, cancel_prescription, create_prescription, dispense_prescription, prescription_for_token


def _active_staff(user, role):
    if user.primary_role != role or not getattr(getattr(user, "staff_profile", None), "active", False):
        raise PermissionDenied


def _dispenser_membership(user):
    _active_staff(user, User.Role.DISPENSER)
    membership = FacilityMembership.objects.select_related("facility").filter(
        user=user, role=User.Role.DISPENSER, active=True, facility__status="active"
    ).first()
    if not membership:
        raise PermissionDenied
    return membership


@roles_required(User.Role.DOCTOR)
def doctor_prescription_list(request):
    _active_staff(request.user, User.Role.DOCTOR)
    Prescription.objects.filter(
        prescriber=request.user, status__in=(Prescription.Status.ACTIVE, Prescription.Status.PARTIAL),
        valid_until__lte=timezone.now(),
    ).update(status=Prescription.Status.EXPIRED)
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
            prescription = create_prescription(form=form, item_formset=formset, prescriber=request.user)
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Prescription issued securely to the patient account.")
            return redirect("doctor_prescription_detail", pk=prescription.pk)
    return render(request, "prescriptions/create.html", {"form": form, "formset": formset})


@roles_required(User.Role.DOCTOR)
def doctor_prescription_detail(request, pk):
    _active_staff(request.user, User.Role.DOCTOR)
    prescription = get_object_or_404(Prescription.objects.prefetch_related("items__medicine"), pk=pk, prescriber=request.user)
    if prescription.status in {Prescription.Status.ACTIVE, Prescription.Status.PARTIAL} and prescription.valid_until <= timezone.now():
        prescription.status = Prescription.Status.EXPIRED
        prescription.save(update_fields=("status",))
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


@roles_required(User.Role.PATIENT)
def patient_prescription_list(request):
    Prescription.objects.filter(
        patient=request.user, status__in=(Prescription.Status.ACTIVE, Prescription.Status.PARTIAL),
        valid_until__lte=timezone.now(),
    ).update(status=Prescription.Status.EXPIRED)
    prescriptions = Prescription.objects.filter(patient=request.user).select_related("prescriber").prefetch_related("items__medicine")
    return render(request, "prescriptions/patient_list.html", {"prescriptions": prescriptions})


@roles_required(User.Role.PATIENT)
def patient_prescription_detail(request, pk):
    prescription = get_object_or_404(Prescription.objects.prefetch_related("items__medicine"), pk=pk, patient=request.user)
    if prescription.status in {Prescription.Status.ACTIVE, Prescription.Status.PARTIAL} and prescription.valid_until <= timezone.now():
        prescription.status = Prescription.Status.EXPIRED
        prescription.save(update_fields=("status",))
    return render(request, "prescriptions/detail.html", {"prescription": prescription, "viewer": "patient"})


def prescription_qr(request, pk):
    if not request.user.is_authenticated:
        raise PermissionDenied
    prescription = get_object_or_404(Prescription, pk=pk)
    if prescription.patient_id != request.user.pk and prescription.prescriber_id != request.user.pk:
        raise PermissionDenied
    return FileResponse(prescription.qr_image.open("rb"), content_type="image/png")


@roles_required(User.Role.DISPENSER)
def dispense_scan(request):
    membership = _dispenser_membership(request.user)
    form = TokenScanForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        return redirect("dispense_verify", token=form.cleaned_data["token"])
    return render(request, "dispensing/scan.html", {"form": form, "facility": membership.facility})


@roles_required(User.Role.DISPENSER)
def dispense_verify(request, token):
    membership = _dispenser_membership(request.user)
    prescription = prescription_for_token(token)
    if prescription is None:
        return render(request, "dispensing/invalid.html", status=404)
    if prescription.status in {Prescription.Status.ACTIVE, Prescription.Status.PARTIAL} and prescription.valid_until <= timezone.now():
        prescription.status = Prescription.Status.EXPIRED
        prescription.save(update_fields=("status",))
    items = list(prescription.items.select_related("medicine"))
    form = DispenseForm(request.POST or None, items=items)
    if request.method == "POST" and form.is_valid():
        try:
            dispense_prescription(
                prescription=prescription, quantities=form.quantities(),
                facility=membership.facility, dispenser=request.user,
            )
        except DispenseError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Dispensing recorded and facility stock updated atomically.")
            return redirect("dispense_verify", token=token)
    prescription.refresh_from_db()
    return render(request, "dispensing/verify.html", {
        "prescription": prescription, "items": items, "form": form, "facility": membership.facility,
    })
