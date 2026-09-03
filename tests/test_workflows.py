from datetime import date, timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook
from apps.accounts.models import PatientProfile, StaffProfile, User
from apps.audit.models import AuditEvent
from apps.facilities.models import Facility, FacilityMembership
from apps.inventory.models import InventoryItem, InventoryUpload
from apps.inventory.services import commit_inventory_upload, validate_inventory_workbook
from apps.medicines.models import Medicine
from apps.prescriptions.models import DispenseEvent, Prescription, PrescriptionItem
from apps.prescriptions.services import DispenseError, dispense_prescription, token_digest


def workbook_upload(rows, headers=None, name="stock.xlsx"):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers or ["medicine_code", "medicine_name", "strength", "form", "quantity", "expiry_date", "last_updated"])
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return SimpleUploadedFile(name, output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class WorkflowFixture(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user("rx-patient", "rx-patient@example.test", "testing-password", primary_role=User.Role.PATIENT)
        PatientProfile.objects.create(user=self.patient, consent_acknowledged=True)
        self.doctor = User.objects.create_user("doctor", "doctor@example.test", "testing-password", primary_role=User.Role.DOCTOR)
        StaffProfile.objects.create(user=self.doctor, active=True)
        self.dispenser = User.objects.create_user("dispenser", "dispenser@example.test", "testing-password", primary_role=User.Role.DISPENSER)
        StaffProfile.objects.create(user=self.dispenser, active=True)
        self.officer = User.objects.create_user("importer", "importer@example.test", "testing-password", primary_role=User.Role.INVENTORY)
        self.facility = Facility.objects.create(
            name="Workflow Clinic", facility_type=Facility.Type.CLINIC, address="Gaborone",
            latitude=-24.65, longitude=25.91, status=Facility.Status.ACTIVE,
        )
        for user, role in ((self.dispenser, User.Role.DISPENSER), (self.officer, User.Role.INVENTORY)):
            FacilityMembership.objects.create(user=user, facility=self.facility, role=role)
        self.medicine = Medicine.objects.create(
            code="MED-RX-1", name="Amoxicillin", generic_name="Amoxicillin",
            strength="500 mg", form="capsule", barcode="600000000011",
        )
        self.stock = InventoryItem.objects.create(
            facility=self.facility, medicine=self.medicine, quantity=25,
            expiry_date=date.today() + timedelta(days=180),
        )

    def make_prescription(self, *, quantity=10, valid_until=None, token="secure-prescription-token-with-enough-entropy-123"):
        prescription = Prescription.objects.create(
            patient=self.patient, prescriber=self.doctor,
            valid_until=valid_until or timezone.now() + timedelta(days=7),
            token_hash=token_digest(token), token_hint=token[-6:], qr_image="qr/test.png",
        )
        item = PrescriptionItem.objects.create(
            prescription=prescription, medicine=self.medicine, dosage="One capsule three times daily",
            prescribed_quantity=quantity,
        )
        return prescription, item, token


class InventoryImportTests(WorkflowFixture):
    def test_valid_and_invalid_rows_are_reported_then_valid_rows_commit(self):
        upload_file = workbook_upload([
            ["MED-RX-1", "Amoxicillin", "500 mg", "capsule", 41, self.stock.expiry_date, ""],
            ["UNKNOWN", "Unknown", "1 mg", "tablet", -2, date.today() + timedelta(days=30), ""],
        ])
        upload = validate_inventory_workbook(uploaded_file=upload_file, facility=self.facility, actor=self.officer)
        self.assertEqual(upload.status, InventoryUpload.Status.VALIDATED)
        self.assertEqual((upload.accepted_count, upload.rejected_count), (1, 1))
        self.assertEqual(self.stock.quantity, 25)
        changed = commit_inventory_upload(upload=upload, actor=self.officer)
        self.stock.refresh_from_db()
        upload.refresh_from_db()
        self.assertEqual(changed, 1)
        self.assertEqual(self.stock.quantity, 41)
        self.assertEqual(upload.status, InventoryUpload.Status.IMPORTED)
        self.assertTrue(AuditEvent.objects.filter(action="inventory.upload_committed").exists())

    def test_bad_headers_reject_whole_workbook(self):
        upload = validate_inventory_workbook(
            uploaded_file=workbook_upload([], headers=["wrong", "quantity"]),
            facility=self.facility, actor=self.officer,
        )
        self.assertEqual(upload.status, InventoryUpload.Status.REJECTED)
        self.assertIn("Missing headers", upload.error_text)

    def test_formula_cell_is_rejected(self):
        upload = validate_inventory_workbook(
            uploaded_file=workbook_upload([["MED-RX-1", "Amoxicillin", "500 mg", "capsule", "=20+1", self.stock.expiry_date, ""]]),
            facility=self.facility, actor=self.officer,
        )
        self.assertEqual(upload.rejected_count, 1)
        self.assertIn("Formula cells", upload.rows.get().error_text)

    def test_same_import_cannot_be_committed_twice(self):
        content = workbook_upload([["MED-RX-1", "Amoxicillin", "500 mg", "capsule", 40, self.stock.expiry_date, ""]]).read()
        first = validate_inventory_workbook(
            uploaded_file=SimpleUploadedFile("first.xlsx", content), facility=self.facility, actor=self.officer
        )
        commit_inventory_upload(upload=first, actor=self.officer)
        repeated = validate_inventory_workbook(
            uploaded_file=SimpleUploadedFile("again.xlsx", content), facility=self.facility, actor=self.officer
        )
        self.assertEqual(repeated.status, InventoryUpload.Status.REJECTED)
        self.assertIn("already been imported", repeated.error_text)


class PrescriptionAccessTests(WorkflowFixture):
    def test_doctor_can_create_multi_item_prescription_with_qr(self):
        other = Medicine.objects.create(code="MED-RX-2", name="Paracetamol", strength="500 mg", form="tablet")
        self.client.force_login(self.doctor)
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(reverse("doctor_prescription_create"), {
                    "patient": self.patient.pk,
                    "valid_until": (timezone.localtime() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M"),
                    "notes": "Synthetic prescription",
                    "items-TOTAL_FORMS": "3", "items-INITIAL_FORMS": "0", "items-MIN_NUM_FORMS": "1", "items-MAX_NUM_FORMS": "1000",
                    "items-0-medicine": self.medicine.pk, "items-0-dosage": "Three times daily", "items-0-prescribed_quantity": 12, "items-0-instructions": "After food",
                    "items-1-medicine": other.pk, "items-1-dosage": "When required", "items-1-prescribed_quantity": 8, "items-1-instructions": "",
                    "items-2-medicine": "", "items-2-dosage": "", "items-2-prescribed_quantity": "", "items-2-instructions": "",
                })
                prescription = Prescription.objects.get(prescriber=self.doctor)
                self.assertRedirects(response, reverse("doctor_prescription_detail", args=[prescription.pk]))
                self.assertEqual(prescription.items.count(), 2)
                self.assertEqual(len(prescription.token_hash), 64)
                self.assertNotIn(self.patient.username, prescription.qr_image.name)
                self.assertTrue(prescription.qr_image.storage.exists(prescription.qr_image.name))

    def test_patient_cannot_read_another_patients_prescription(self):
        prescription, _, _ = self.make_prescription()
        other = User.objects.create_user("other-patient", "other@example.test", "testing-password", primary_role=User.Role.PATIENT)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("patient_prescription_detail", args=[prescription.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("prescription_qr", args=[prescription.pk])).status_code, 403)

    def test_dispenser_can_resolve_valid_opaque_token(self):
        _, _, token = self.make_prescription()
        self.client.force_login(self.dispenser)
        response = self.client.get(reverse("dispense_verify", args=[token]))
        self.assertContains(response, "Amoxicillin")

    def test_prescribing_doctor_can_cancel_but_another_doctor_cannot(self):
        prescription, _, _ = self.make_prescription()
        other_doctor = User.objects.create_user(
            "other-doctor", "other-doctor@example.test", "testing-password", primary_role=User.Role.DOCTOR
        )
        StaffProfile.objects.create(user=other_doctor, active=True)
        self.client.force_login(other_doctor)
        self.assertEqual(
            self.client.post(reverse("doctor_prescription_cancel", args=[prescription.pk])).status_code, 404
        )
        self.client.force_login(self.doctor)
        response = self.client.post(reverse("doctor_prescription_cancel", args=[prescription.pk]))
        self.assertRedirects(response, reverse("doctor_prescription_detail", args=[prescription.pk]))
        prescription.refresh_from_db()
        self.assertEqual(prescription.status, Prescription.Status.CANCELLED)
        self.assertTrue(AuditEvent.objects.filter(action="prescription.cancelled").exists())


class DispensingTests(WorkflowFixture):
    def test_partial_then_full_dispense_updates_every_record(self):
        prescription, item, _ = self.make_prescription(quantity=10)
        dispense_prescription(prescription=prescription, quantities={item.pk: 4}, facility=self.facility, dispenser=self.dispenser)
        prescription.refresh_from_db(); item.refresh_from_db(); self.stock.refresh_from_db()
        self.assertEqual((prescription.status, item.status, item.dispensed_quantity, self.stock.quantity),
                         (Prescription.Status.PARTIAL, PrescriptionItem.Status.PARTIAL, 4, 21))
        dispense_prescription(prescription=prescription, quantities={item.pk: 6}, facility=self.facility, dispenser=self.dispenser)
        prescription.refresh_from_db(); item.refresh_from_db(); self.stock.refresh_from_db()
        self.assertEqual((prescription.status, item.status, item.dispensed_quantity, self.stock.quantity),
                         (Prescription.Status.DISPENSED, PrescriptionItem.Status.FULFILLED, 10, 15))
        self.assertEqual(DispenseEvent.objects.filter(item=item).count(), 2)

    def test_insufficient_second_item_rolls_back_first_item_and_stock(self):
        prescription, item, _ = self.make_prescription(quantity=10)
        other = Medicine.objects.create(code="MED-RX-3", name="ORS", strength="20 g", form="sachet")
        other_item = PrescriptionItem.objects.create(
            prescription=prescription, medicine=other, dosage="As directed", prescribed_quantity=5
        )
        InventoryItem.objects.create(
            facility=self.facility, medicine=other, quantity=1, expiry_date=date.today() + timedelta(days=90)
        )
        with self.assertRaises(DispenseError):
            dispense_prescription(
                prescription=prescription, quantities={item.pk: 3, other_item.pk: 5},
                facility=self.facility, dispenser=self.dispenser,
            )
        item.refresh_from_db(); self.stock.refresh_from_db()
        self.assertEqual(item.dispensed_quantity, 0)
        self.assertEqual(self.stock.quantity, 25)
        self.assertFalse(DispenseEvent.objects.exists())

    def test_expired_prescription_cannot_be_dispensed(self):
        prescription, item, _ = self.make_prescription(valid_until=timezone.now() - timedelta(minutes=1))
        with self.assertRaises(DispenseError):
            dispense_prescription(
                prescription=prescription, quantities={item.pk: 1},
                facility=self.facility, dispenser=self.dispenser,
            )
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 25)

    def test_fully_dispensed_prescription_cannot_be_reused(self):
        prescription, item, _ = self.make_prescription(quantity=2)
        dispense_prescription(
            prescription=prescription, quantities={item.pk: 2}, facility=self.facility, dispenser=self.dispenser
        )
        with self.assertRaises(DispenseError):
            dispense_prescription(
                prescription=prescription, quantities={item.pk: 1}, facility=self.facility, dispenser=self.dispenser
            )
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 23)
