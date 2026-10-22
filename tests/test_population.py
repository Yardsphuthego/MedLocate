from io import StringIO
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.models import StaffProfile, User
from apps.audit.models import AuditEvent
from apps.facilities.models import Facility
from apps.inventory.models import InventoryAdjustment, InventoryItem, InventoryUpload
from apps.medicines.models import Medicine
from apps.prescriptions.models import DispenseEvent, Prescription


class WorkspacePopulationTests(TestCase):
    def test_synthetic_records_are_connected_and_repeatable(self):
        for role in (User.Role.DOCTOR, User.Role.NURSE, User.Role.PHARMACY, User.Role.INVENTORY, User.Role.DISPENSER):
            user = User.objects.create_user(
                username=f"demo.{role}", email=f"demo.{role}@example.test",
                password="existing-password", primary_role=role,
            )
            StaffProfile.objects.create(user=user)

        with TemporaryDirectory() as media, override_settings(DEBUG=True, MEDIA_ROOT=media):
            call_command("populate_workspace", "--apply", stdout=StringIO())
            first_counts = tuple(model.objects.count() for model in (
                Facility, Medicine, InventoryItem, InventoryUpload, InventoryAdjustment,
                Prescription, DispenseEvent, AuditEvent,
            ))
            self.assertEqual(first_counts[:4], (6, 13, 78, 3))
            self.assertEqual(Prescription.objects.count(), 8)
            self.assertEqual(DispenseEvent.objects.count(), 4)
            self.assertEqual(InventoryUpload.objects.filter(status=InventoryUpload.Status.IMPORTED).count(), 2)
            self.assertEqual(InventoryUpload.objects.filter(status=InventoryUpload.Status.REJECTED).count(), 1)
            self.assertEqual(Prescription.objects.filter(status=Prescription.Status.PARTIAL).count(), 2)
            self.assertEqual(Prescription.objects.filter(status=Prescription.Status.DISPENSED).count(), 2)
            self.assertTrue(all(record.qr_image.storage.exists(record.qr_image.name) for record in Prescription.objects.all()))

            call_command("populate_workspace", "--apply", stdout=StringIO())
            self.assertEqual(first_counts, tuple(model.objects.count() for model in (
                Facility, Medicine, InventoryItem, InventoryUpload, InventoryAdjustment,
                Prescription, DispenseEvent, AuditEvent,
            )))
            self.assertTrue(User.objects.get(username="demo.doctor").check_password("existing-password"))
