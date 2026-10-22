"""Add connected synthetic records to a local MedLocate workspace."""

from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from openpyxl import Workbook

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.facilities.models import Facility, FacilityMembership
from apps.inventory.models import InventoryItem, InventoryUpload
from apps.inventory.services import commit_inventory_upload, validate_inventory_workbook
from apps.medicines.models import Medicine
from apps.prescriptions.forms import PrescriptionForm, PrescriptionItemFormSet
from apps.prescriptions.models import Prescription
from apps.prescriptions.services import cancel_prescription, create_prescription, dispense_prescription


FACILITIES = (
    ("Gaborone Central Clinic", Facility.Type.CLINIC, "Central Gaborone", -24.6581, 25.9122),
    ("Block 8 Community Clinic", Facility.Type.CLINIC, "Block 8, Gaborone", -24.6047, 25.9252),
    ("Princess Marina Hospital", Facility.Type.HOSPITAL, "Independence Avenue, Gaborone", -24.6543, 25.9194),
    ("MedLocate Pilot Clinic — Francistown", Facility.Type.CLINIC, "Francistown pilot area", -21.1700, 27.5100),
    ("MedLocate Pilot Pharmacy — Maun", Facility.Type.PHARMACY, "Maun pilot area", -19.9800, 23.4200),
    ("MedLocate Pilot Clinic — Molepolole", Facility.Type.CLINIC, "Molepolole pilot area", -24.4000, 25.4900),
)

MEDICINES = (
    ("MED-PAR-500", "Paracetamol", "500 mg", "tablet"),
    ("MED-AMX-500", "Amoxicillin", "500 mg", "capsule"),
    ("MED-ORS-001", "Oral rehydration salts", "20.5 g", "sachet"),
    ("MLP-IBU-200", "Ibuprofen", "200 mg", "tablet"),
    ("MLP-MET-500", "Metformin", "500 mg", "tablet"),
    ("MLP-AML-005", "Amlodipine", "5 mg", "tablet"),
    ("MLP-LOS-050", "Losartan", "50 mg", "tablet"),
    ("MLP-OMZ-020", "Omeprazole", "20 mg", "capsule"),
    ("MLP-CET-010", "Cetirizine", "10 mg", "tablet"),
    ("MLP-AZT-250", "Azithromycin", "250 mg", "tablet"),
    ("MLP-SAL-100", "Salbutamol", "100 mcg", "inhaler"),
    ("MLP-FER-200", "Ferrous sulfate", "200 mg", "tablet"),
    ("MLP-ZNC-020", "Zinc sulfate", "20 mg", "tablet"),
)

MEMBERSHIPS = (
    ("demo.doctor", 1), ("demo.doctor", 2), ("demo.doctor", 3),
    ("demo.nurse", 0), ("demo.nurse", 1), ("demo.nurse", 3),
    ("demo.pharmacy", 1), ("demo.pharmacy", 2), ("demo.pharmacy", 4),
    ("demo.inventory", 0), ("demo.inventory", 1), ("demo.inventory", 2), ("demo.inventory", 5),
    ("demo.dispenser", 0), ("demo.dispenser", 5),
)

PRESCRIPTIONS = (
    ("MLP-RX-01", (("MED-PAR-500", 12),), "active", None),
    ("MLP-RX-02", (("MED-AMX-500", 15),), "active", None),
    ("MLP-RX-03", (("MLP-MET-500", 30),), "active", None),
    ("MLP-RX-04", (("MLP-IBU-200", 20),), "partial", ("demo.pharmacy", 1, 8)),
    ("MLP-RX-05", (("MED-ORS-001", 10),), "dispensed", ("demo.dispenser", 0, 10)),
    ("MLP-RX-06", (("MED-PAR-500", 10),), "dispensed", ("demo.nurse", 1, 10)),
    ("MLP-RX-07", (("MLP-AML-005", 20),), "cancelled", None),
    ("MLP-RX-08", (("MED-PAR-500", 10), ("MLP-MET-500", 10)), "partial", ("demo.pharmacy", 1, 5)),
)


def _pilot_barcode(index):
    body = f"299000000{index:03d}"
    checksum = (10 - sum(int(digit) * (3 if position % 2 else 1) for position, digit in enumerate(body)) % 10) % 10
    return body + str(checksum)


def _workbook(name, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(("medicine_code", "medicine_name", "strength", "form", "quantity", "expiry_date", "batch_number"))
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return SimpleUploadedFile(name, output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class Command(BaseCommand):
    help = "Add repeatable synthetic facilities, stock, imports and prescription activity to a development database."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Confirm that synthetic records may be written to this development database.")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Synthetic records may only be populated in a development environment.")
        if not options["apply"]:
            raise CommandError("Pass --apply to populate this development database with synthetic records.")

        required = {username for username, _ in MEMBERSHIPS}
        users = User.objects.in_bulk(required, field_name="username")
        if len(users) != len(required):
            raise CommandError("The demo professional accounts are required before populating records.")
        for username, user in users.items():
            if not user.is_active or not getattr(getattr(user, "staff_profile", None), "active", False):
                raise CommandError(f"{username} must be an active professional account.")

        with transaction.atomic():
            facilities = []
            for name, kind, address, latitude, longitude in FACILITIES:
                facility, _ = Facility.objects.get_or_create(name=name, defaults={
                    "facility_type": kind, "address": address, "latitude": latitude,
                    "longitude": longitude, "status": Facility.Status.ACTIVE,
                })
                facilities.append(facility)

            medicines = {}
            for index, (code, name, strength, form) in enumerate(MEDICINES, start=1):
                medicine, _ = Medicine.objects.get_or_create(code=code, defaults={
                    "name": name, "generic_name": name, "strength": strength, "form": form,
                    "barcode": _pilot_barcode(index) if code.startswith("MLP-") else None,
                    "active": True,
                })
                medicines[code] = medicine

            for username, facility_index in MEMBERSHIPS:
                user = users[username]
                FacilityMembership.objects.get_or_create(
                    user=user, facility=facilities[facility_index], role=user.primary_role,
                    defaults={"active": True},
                )

            today = timezone.localdate()
            for facility_index, facility in enumerate(facilities):
                for medicine_index, (code, _, _, _) in enumerate(MEDICINES):
                    if facility_index < 3 and medicine_index < 3:
                        if InventoryItem.objects.filter(facility=facility, medicine=medicines[code]).exists():
                            continue  # Existing stock remains untouched.
                        quantity, expiry_days = 40 + facility_index * 5 + medicine_index * 4, 180
                    else:
                        pattern = (facility_index * 3 + medicine_index) % 11
                        quantity = 0 if pattern in (0, 2) else 5 if pattern == 1 else 24 + facility_index * 5 + medicine_index * 2
                        expiry_days = -5 if pattern == 2 else 21 if pattern == 3 else 180 + medicine_index * 9
                    InventoryItem.objects.get_or_create(
                        facility=facility, medicine=medicines[code],
                        batch_number=f"MLP-{facility_index + 1:02d}-{medicine_index + 1:02d}",
                        defaults={"quantity": quantity, "expiry_date": today + timedelta(days=expiry_days),
                                  "low_stock_threshold": 10, "updated_by": users["demo.inventory"]},
                    )

            self._imports(facilities, medicines, users)
            self._prescriptions(facilities, medicines, users)

        self.stdout.write(self.style.SUCCESS(
            f"Workspace populated: {Facility.objects.count()} facilities, {Medicine.objects.count()} medicines, "
            f"{InventoryItem.objects.count()} stock records, {InventoryUpload.objects.count()} imports, "
            f"{Prescription.objects.count()} prescriptions and {AuditEvent.objects.count()} audit events."
        ))

    def _imports(self, facilities, medicines, users):
        for facility_index, actor_name, name in (
            (0, "demo.inventory", "medlocate-pilot-gaborone.xlsx"),
            (1, "demo.pharmacy", "medlocate-pilot-block8.xlsx"),
        ):
            facility = facilities[facility_index]
            if InventoryUpload.objects.filter(facility=facility, original_name=name).exists():
                continue
            rows = []
            for code in ("MLP-IBU-200", "MLP-MET-500", "MLP-AML-005"):
                medicine_index = next(index for index, data in enumerate(MEDICINES) if data[0] == code)
                item = InventoryItem.objects.get(
                    facility=facility, medicine=medicines[code],
                    batch_number=f"MLP-{facility_index + 1:02d}-{medicine_index + 1:02d}",
                )
                rows.append((code, item.medicine.name, item.medicine.strength, item.medicine.form,
                             max(item.quantity + 8, 18), item.expiry_date, item.batch_number))
            upload = validate_inventory_workbook(
                uploaded_file=_workbook(name, rows), facility=facility, actor=users[actor_name],
            )
            if upload.status != InventoryUpload.Status.VALIDATED:
                raise CommandError(f"Synthetic workbook validation failed: {upload.error_text}")
            commit_inventory_upload(upload=upload, actor=users[actor_name])

        facility = facilities[4]
        name = "medlocate-pilot-rejected.xlsx"
        if not InventoryUpload.objects.filter(facility=facility, original_name=name).exists():
            validate_inventory_workbook(
                uploaded_file=_workbook(name, [("UNKNOWN-PILOT", "Unknown", "1 mg", "tablet", 10,
                                                timezone.localdate() + timedelta(days=90), "MLP-INVALID")]),
                facility=facility, actor=users["demo.pharmacy"],
            )

    def _prescriptions(self, facilities, medicines, users):
        doctor = users["demo.doctor"]
        for index, (reference, lines, target_status, dispense) in enumerate(PRESCRIPTIONS, start=1):
            prescription = Prescription.objects.filter(recipient_reference=reference).first()
            if prescription is None:
                expires = timezone.localtime(timezone.now() + timedelta(days=7))
                form = PrescriptionForm(data={
                    "recipient_name": f"Sample Recipient {index:02d}",
                    "recipient_reference": reference,
                    "valid_until": expires.strftime("%Y-%m-%dT%H:%M"),
                    "notes": "Synthetic pilot record. Not for patient care.",
                })
                data = {"items-TOTAL_FORMS": "3", "items-INITIAL_FORMS": "0",
                        "items-MIN_NUM_FORMS": "1", "items-MAX_NUM_FORMS": "1000"}
                for position, (code, quantity) in enumerate(lines):
                    data.update({f"items-{position}-medicine": str(medicines[code].pk),
                                 f"items-{position}-dosage": "Synthetic directions",
                                 f"items-{position}-prescribed_quantity": str(quantity),
                                 f"items-{position}-instructions": "Training record only"})
                formset = PrescriptionItemFormSet(data=data, prefix="items")
                if not form.is_valid() or not formset.is_valid():
                    raise CommandError(f"Synthetic prescription {reference} is invalid: {form.errors} {formset.errors}")
                prescription = create_prescription(
                    form=form, item_formset=formset, prescriber=doctor, facility_id=facilities[1].pk,
                )

            if dispense and prescription.status == Prescription.Status.ACTIVE:
                actor_name, facility_index, quantity = dispense
                actor, facility = users[actor_name], facilities[facility_index]
                if not AuditEvent.objects.filter(action="prescription.verified", object_type=prescription._meta.label,
                                                  object_id=str(prescription.pk), facility=facility).exists():
                    record_event(actor=actor, action="prescription.verified", obj=prescription, facility=facility,
                                 metadata={"synthetic": True})
                item = prescription.items.get(medicine=medicines[lines[0][0]])
                dispense_prescription(prescription=prescription, quantities={item.pk: quantity},
                                      facility=facility, dispenser=actor)
            elif target_status == "cancelled" and prescription.status == Prescription.Status.ACTIVE:
                cancel_prescription(prescription=prescription, actor=doctor)
