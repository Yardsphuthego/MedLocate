import hmac
import secrets
from hashlib import sha256
from io import BytesIO
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.utils import timezone
import qrcode
from PIL import Image, ImageDraw
from apps.audit.services import record_event
from apps.inventory.models import InventoryAdjustment, InventoryItem
from .models import DispenseAllocation, DispenseEvent, DispenseTransaction, Prescription, PrescriptionItem
from apps.accounts.access import require_staff, require_membership, DISPENSE_ROLES
from apps.accounts.models import User


class DispenseError(ValueError):
    pass


def token_digest(token):
    return hmac.new(settings.SECRET_KEY.encode(), token.encode(), sha256).hexdigest()


@transaction.atomic
def create_prescription(*, form, item_formset, prescriber, facility_id=None):
    require_staff(prescriber, {User.Role.DOCTOR})
    prescription = form.save(commit=False)
    prescription.prescriber = prescriber
    from apps.facilities.models import FacilityMembership
    membership = require_membership(prescriber, {User.Role.DOCTOR}, facility_id) if facility_id else FacilityMembership.objects.filter(user=prescriber, role=User.Role.DOCTOR, active=True, facility__status="active").order_by("facility__name", "pk").first()
    prescription.issuing_facility = membership.facility if membership else None
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
    qr_url = token
    qr = qrcode.make(qr_url).convert("RGB")
    image = Image.new("RGB", (max(qr.width, 360), qr.height + 54), "white")
    image.paste(qr, ((image.width - qr.width) // 2, 0))
    draw = ImageDraw.Draw(image)
    draw.text((12, qr.height + 6), "Reference (enter without spaces):", fill="black")
    draw.text((12, qr.height + 26), token, fill="black")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    prescription.qr_image.save(f"prescription-{prescription.uuid}.png", ContentFile(buffer.getvalue()), save=True)
    record_event(actor=prescriber, action="prescription.created", obj=prescription,
                 metadata={"item_count": prescription.items.count()})
    return prescription


def prescription_for_token(token):
    return Prescription.objects.filter(token_hash=token_digest(token)).select_related("patient", "prescriber").first()


@transaction.atomic
def dispense_prescription(*, prescription, quantities, facility, dispenser, confirmation_key=None):
    require_membership(dispenser, DISPENSE_ROLES, facility)
    prescription = Prescription.objects.select_for_update().get(pk=prescription.pk)
    payload = {str(key): value for key, value in quantities.items()}
    if confirmation_key:
        prior = DispenseTransaction.objects.filter(key=confirmation_key).first()
        if prior:
            if (prior.prescription_id != prescription.pk or prior.facility_id != facility.pk
                    or prior.actor_id != dispenser.pk or prior.quantities != payload):
                raise DispenseError("This confirmation has already been used for a different transaction.")
            return prescription
    if not quantities:
        raise DispenseError("Enter a quantity for at least one prescription item.")
    if prescription.valid_until <= timezone.now():
        raise DispenseError("This prescription has expired.")
    if prescription.status not in {Prescription.Status.ACTIVE, Prescription.Status.PARTIAL}:
        raise DispenseError("This prescription is not available for dispensing.")
    if confirmation_key:
        try:
            with transaction.atomic():
                DispenseTransaction.objects.create(key=confirmation_key, prescription=prescription,
                                                  facility=facility, actor=dispenser, quantities=payload)
        except IntegrityError as exc:
            raise DispenseError("This confirmation has already been used.") from exc
    items = {item.pk: item for item in PrescriptionItem.objects.select_for_update(of=("self",)).filter(prescription=prescription).select_related("medicine").order_by("medicine_id")}
    for item_id, requested in sorted(quantities.items(), key=lambda pair: items[pair[0]].medicine_id if pair[0] in items else -1):
        item = items.get(item_id)
        if not item or not isinstance(requested, int) or isinstance(requested, bool) or requested < 1 or requested > item.remaining_quantity:
            raise DispenseError("A dispense quantity is no longer valid. Refresh and try again.")
        stocks = list(InventoryItem.objects.select_for_update().filter(
            facility=facility, medicine=item.medicine, quantity__gt=0
        ).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=timezone.localdate())).order_by("expiry_date", "pk"))
        if sum(stock.quantity for stock in stocks) < requested:
            raise DispenseError(f"{facility.name} does not have enough {item.medicine.name} stock.")
        allocations = []
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
            allocations.append((stock, used))
            remaining -= used
        item.dispensed_quantity += requested
        item.status = PrescriptionItem.Status.FULFILLED if item.remaining_quantity == 0 else PrescriptionItem.Status.PARTIAL
        item.save(update_fields=("dispensed_quantity", "status"))
        event = DispenseEvent.objects.create(item=item, facility=facility, quantity=requested, dispensed_by=dispenser)
        DispenseAllocation.objects.bulk_create([DispenseAllocation(event=event, stock=stock, quantity=used) for stock, used in allocations])
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
    if not prescription.is_usable:
        raise ValueError("Only an active or partially dispensed prescription can be cancelled.")
    prescription.status = Prescription.Status.CANCELLED
    prescription.save(update_fields=("status",))
    record_event(actor=actor, action="prescription.cancelled", obj=prescription,
                 metadata={"had_partial_dispense": prescription.items.filter(dispensed_quantity__gt=0).exists()})
    return prescription
