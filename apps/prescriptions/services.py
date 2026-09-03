import hmac
import secrets
from hashlib import sha256
from io import BytesIO
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
import qrcode
from apps.audit.services import record_event
from apps.inventory.models import InventoryAdjustment, InventoryItem
from .models import DispenseEvent, Prescription, PrescriptionItem


class DispenseError(ValueError):
    pass


def token_digest(token):
    return hmac.new(settings.SECRET_KEY.encode(), token.encode(), sha256).hexdigest()


@transaction.atomic
def create_prescription(*, form, item_formset, prescriber):
    prescription = form.save(commit=False)
    prescription.prescriber = prescriber
    prescription.status = Prescription.Status.ACTIVE
    token = secrets.token_urlsafe(32)
    prescription.token_hash = token_digest(token)
    prescription.token_hint = token[-6:]
    prescription.full_clean(exclude=("qr_image",))
    prescription.save()
    seen = set()
    for item_data in item_formset.cleaned_data:
        if not item_data:
            continue
        medicine = item_data["medicine"]
        if medicine.pk in seen:
            raise ValueError("A medicine can appear only once on a prescription.")
        seen.add(medicine.pk)
        PrescriptionItem.objects.create(
            prescription=prescription, medicine=medicine, dosage=item_data["dosage"],
            instructions=item_data["instructions"], prescribed_quantity=item_data["prescribed_quantity"],
        )
    qr_url = f"{settings.MEDLOCATE_PUBLIC_URL}/dispense/verify/{token}/"
    image = qrcode.make(qr_url)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    prescription.qr_image.save(f"prescription-{prescription.uuid}.png", ContentFile(buffer.getvalue()), save=True)
    record_event(actor=prescriber, action="prescription.created", obj=prescription,
                 metadata={"item_count": prescription.items.count()})
    return prescription


def prescription_for_token(token):
    return Prescription.objects.filter(token_hash=token_digest(token)).select_related("patient", "prescriber").first()


@transaction.atomic
def dispense_prescription(*, prescription, quantities, facility, dispenser):
    prescription = Prescription.objects.select_for_update().get(pk=prescription.pk)
    if not quantities:
        raise DispenseError("Enter a quantity for at least one prescription item.")
    if prescription.valid_until <= timezone.now():
        if prescription.status in {Prescription.Status.ACTIVE, Prescription.Status.PARTIAL}:
            prescription.status = Prescription.Status.EXPIRED
            prescription.save(update_fields=("status",))
        raise DispenseError("This prescription has expired.")
    if prescription.status not in {Prescription.Status.ACTIVE, Prescription.Status.PARTIAL}:
        raise DispenseError("This prescription is not available for dispensing.")
    items = {item.pk: item for item in PrescriptionItem.objects.select_for_update().filter(prescription=prescription).select_related("medicine")}
    for item_id, requested in quantities.items():
        item = items.get(item_id)
        if not item or requested < 1 or requested > item.remaining_quantity:
            raise DispenseError("A dispense quantity is no longer valid. Refresh and try again.")
        stocks = list(InventoryItem.objects.select_for_update().filter(
            facility=facility, medicine=item.medicine, quantity__gt=0
        ).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=timezone.localdate())).order_by("expiry_date", "pk"))
        if sum(stock.quantity for stock in stocks) < requested:
            raise DispenseError(f"{facility.name} does not have enough {item.medicine.name} stock.")
        remaining = requested
        for stock in stocks:
            if not remaining:
                break
            used = min(stock.quantity, remaining)
            previous = stock.quantity
            stock.quantity -= used
            stock.updated_by = dispenser
            stock.save(update_fields=("quantity", "updated_by", "updated_at"))
            InventoryAdjustment.objects.create(
                item=stock, previous_quantity=previous, new_quantity=stock.quantity,
                reason=f"Dispensed against prescription {str(prescription.uuid)[:8]}", actor=dispenser,
            )
            remaining -= used
        item.dispensed_quantity += requested
        item.status = PrescriptionItem.Status.FULFILLED if item.remaining_quantity == 0 else PrescriptionItem.Status.PARTIAL
        item.save(update_fields=("dispensed_quantity", "status"))
        DispenseEvent.objects.create(item=item, facility=facility, quantity=requested, dispensed_by=dispenser)
    if all(item.remaining_quantity == 0 for item in items.values()):
        prescription.status = Prescription.Status.DISPENSED
    else:
        prescription.status = Prescription.Status.PARTIAL
    prescription.save(update_fields=("status",))
    record_event(actor=dispenser, action="prescription.dispensed", obj=prescription, facility=facility,
                 metadata={"line_count": len(quantities), "status": prescription.status})
    return prescription


@transaction.atomic
def cancel_prescription(*, prescription, actor):
    prescription = Prescription.objects.select_for_update().get(pk=prescription.pk, prescriber=actor)
    if prescription.status not in {Prescription.Status.ACTIVE, Prescription.Status.PARTIAL}:
        raise ValueError("Only an active or partially dispensed prescription can be cancelled.")
    prescription.status = Prescription.Status.CANCELLED
    prescription.save(update_fields=("status",))
    record_event(actor=actor, action="prescription.cancelled", obj=prescription,
                 metadata={"had_partial_dispense": prescription.items.filter(dispensed_quantity__gt=0).exists()})
    return prescription
