from datetime import date, timedelta
from django.test import TestCase, override_settings
from django.urls import reverse
from apps.accounts.models import PatientProfile, StaffProfile, User
from apps.audit.models import AuditEvent
from apps.facilities.models import Facility, FacilityMembership
from apps.inventory.models import InventoryItem
from apps.medicines.models import Medicine, MedicineAlias
from apps.search.models import SearchHistory
from apps.search.services import haversine_km, search_stock


class CoreFixture(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="patient", email="patient@example.test", password="correct-horse-battery",
            primary_role=User.Role.PATIENT,
        )
        PatientProfile.objects.create(user=self.patient, retain_search_history=True)
        self.officer = User.objects.create_user(
            username="officer", email="officer@example.test", password="correct-horse-battery",
            primary_role=User.Role.INVENTORY,
        )
        StaffProfile.objects.create(user=self.officer)
        self.facility = Facility.objects.create(
            name="Test Clinic", facility_type=Facility.Type.CLINIC, address="Gaborone",
            latitude=-24.65, longitude=25.91, status=Facility.Status.ACTIVE,
        )
        self.other_facility = Facility.objects.create(
            name="Other Clinic", facility_type=Facility.Type.CLINIC, address="Molepolole",
            latitude=-24.40, longitude=25.50, status=Facility.Status.ACTIVE,
        )
        FacilityMembership.objects.create(
            user=self.officer, facility=self.facility, role=User.Role.INVENTORY,
        )
        self.medicine = Medicine.objects.create(
            code="MED-001", name="Paracetamol", generic_name="Acetaminophen",
            strength="500 mg", form="tablet", barcode="600000000001",
        )
        MedicineAlias.objects.create(medicine=self.medicine, name="Panado")
        self.item = InventoryItem.objects.create(
            facility=self.facility, medicine=self.medicine, quantity=25,
            expiry_date=date.today() + timedelta(days=90),
        )


class SearchTests(CoreFixture):
    def test_searches_name_generic_alias_code_and_barcode(self):
        for query in ("Paracetamol", "Acetaminophen", "Panado", "MED-001", "600000000001"):
            with self.subTest(query=query):
                self.assertEqual(search_stock(query)[0]["item"], self.item)

    def test_search_excludes_zero_expired_and_inactive_stock(self):
        self.item.quantity = 0
        self.item.save()
        self.assertEqual(search_stock("Paracetamol"), [])
        self.item.quantity = 5
        self.item.expiry_date = date.today() - timedelta(days=1)
        self.item.save()
        self.assertEqual(search_stock("Paracetamol"), [])

    def test_haversine_distance_is_reasonable(self):
        distance = haversine_km(-24.65, 25.91, -24.60, 25.93)
        self.assertGreater(distance, 5)
        self.assertLess(distance, 7)

    def test_patient_search_is_closed(self):
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(reverse("medicine_search"), {"q": "Panado"}).status_code, 403)
        self.assertEqual(SearchHistory.objects.count(), 0)

    def test_guest_must_sign_in(self):
        response = self.client.get(reverse("medicine_search"), {"q": "Panado"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SearchHistory.objects.count(), 0)

    def test_non_patient_cannot_use_patient_search(self):
        self.client.force_login(self.officer)
        self.assertEqual(self.client.get(reverse("medicine_search")).status_code, 403)


class InventorySecurityTests(CoreFixture):
    def test_officer_sees_only_assigned_facility(self):
        InventoryItem.objects.create(
            facility=self.other_facility, medicine=self.medicine, quantity=99,
            expiry_date=date.today() + timedelta(days=60),
        )
        self.client.force_login(self.officer)
        response = self.client.get(reverse("inventory_list"))
        self.assertContains(response, "Test Clinic")
        self.assertNotContains(response, "Other Clinic")

    def test_patient_cannot_open_inventory(self):
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(reverse("inventory_list")).status_code, 403)

    def test_update_creates_adjustment_and_audit(self):
        self.client.force_login(self.officer)
        response = self.client.post(reverse("inventory_edit", args=[self.item.pk]), {
            "medicine": self.medicine.pk, "quantity": 19,
            "expiry_date": self.item.expiry_date.isoformat(), "low_stock_threshold": 10,
            "reason": "Cycle count correction",
        })
        self.assertRedirects(response, reverse("inventory_list"))
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 19)
        self.assertEqual(self.item.adjustments.get().previous_quantity, 25)
        self.assertTrue(AuditEvent.objects.filter(action="inventory.updated", object_id=str(self.item.pk)).exists())

    def test_cross_facility_edit_returns_404(self):
        other_item = InventoryItem.objects.create(
            facility=self.other_facility, medicine=self.medicine, quantity=4,
            expiry_date=date.today() + timedelta(days=30),
        )
        self.client.force_login(self.officer)
        self.assertEqual(self.client.get(reverse("inventory_edit", args=[other_item.pk])).status_code, 404)

    def test_duplicate_stock_batch_is_rejected_cleanly(self):
        self.client.force_login(self.officer)
        response = self.client.post(reverse("inventory_create"), {
            "medicine": self.medicine.pk, "quantity": 19,
            "expiry_date": self.item.expiry_date.isoformat(), "low_stock_threshold": 10,
            "reason": "Duplicate attempt",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already has a stock record")
        self.assertEqual(InventoryItem.objects.filter(facility=self.facility, medicine=self.medicine).count(), 1)


class DashboardTests(CoreFixture):
    def test_patient_cannot_open_staff_dashboard(self):
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)

    def test_inventory_dashboard_respects_facility_scope(self):
        self.client.force_login(self.officer)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Test Clinic")
        self.assertNotContains(response, "Other Clinic")

    def test_superuser_receives_platform_dashboard(self):
        administrator = User.objects.create_superuser(
            username="platform.admin", email="platform@example.test", password="strong-admin-password"
        )
        administrator.primary_role = User.Role.PLATFORM_ADMIN
        administrator.save(update_fields=["primary_role"])
        self.client.force_login(administrator)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "<h1>Operations</h1>", html=True)
        self.assertContains(response, "Test Clinic")
        self.assertContains(response, "Other Clinic")


class RegistrationTests(TestCase):
    def test_login_opens_home_overlay(self):
        self.assertRedirects(self.client.get(reverse("login")), "/#sign-in")

    def test_public_registration_is_closed(self):
        self.assertEqual(self.client.get(reverse("register")).status_code, 410)
        self.assertEqual(self.client.post(reverse("register"), {"username": "new.patient"}).status_code, 410)
        self.assertFalse(User.objects.filter(username="new.patient").exists())
