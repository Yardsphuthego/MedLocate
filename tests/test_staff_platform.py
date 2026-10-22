import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User, StaffProfile
from apps.facilities.models import Facility, FacilityMembership
from apps.inventory.models import InventoryItem
from apps.prescriptions.models import DispenseAllocation, DispenseEvent, DispenseTransaction, Prescription, PrescriptionItem
from apps.prescriptions.services import DispenseError, dispense_prescription, token_digest
from apps.search.models import SearchHistory
from tests.test_workflows import WorkflowFixture, workbook_upload
from apps.inventory.services import validate_inventory_workbook, commit_inventory_upload


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StaffPlatformTests(WorkflowFixture):
    def setUp(self):
        super().setUp()
        self.nurse = User.objects.create_user('nurse', 'nurse@example.test', 'testing-password', primary_role=User.Role.NURSE)
        self.pharmacy = User.objects.create_user('pharmacy', 'pharmacy@example.test', 'testing-password', primary_role=User.Role.PHARMACY)
        for user in (self.nurse, self.pharmacy):
            StaffProfile.objects.create(user=user)
            FacilityMembership.objects.create(user=user, facility=self.facility, role=user.primary_role)

    def test_search_access_matrix_and_location_not_saved(self):
        for user, expected in [(self.patient, 403), (self.pharmacy, 403), (self.nurse, 200), (self.doctor, 200)]:
            self.client.force_login(user)
            response = self.client.post(reverse('medicine_search'), {'q': 'Amoxicillin', 'lat': '-24.65', 'lon': '25.91'})
            self.assertEqual(response.status_code, expected)
            if expected == 200:
                self.assertContains(response, 'Workflow Clinic')
                self.assertContains(response, 'estimated')
                self.assertNotIn('lat', self.client.session)
        self.assertFalse(SearchHistory.objects.exists())

    def test_distance_precedes_freshness_and_manual_start_works(self):
        far = Facility.objects.create(name='Far away', address='Far', facility_type='clinic', status='active', latitude=-20, longitude=25)
        InventoryItem.objects.create(facility=far, medicine=self.medicine, quantity=10)
        InventoryItem.objects.filter(pk=self.stock.pk).update(updated_at=timezone.now() - timedelta(days=10))
        self.client.force_login(self.nurse)
        response = self.client.post(reverse('medicine_search'), {'q': 'Amoxicillin', 'origin': self.facility.pk})
        self.assertEqual(response.context['results'][0]['item'], self.stock)
        invalid = self.client.post(reverse('medicine_search'), {'q': 'Amoxicillin', 'lat': 'nan', 'lon': '500'})
        self.assertContains(invalid, 'Invalid coordinates')
        self.assertEqual(len(invalid.context['results']), 2)

    def test_revoked_staff_and_suspended_facilities_are_denied(self):
        self.nurse.staff_profile.active = False
        self.nurse.staff_profile.save()
        self.client.force_login(self.nurse)
        for name in ('medicine_search', 'dashboard', 'dispense_scan', 'staff_reports'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.client.force_login(self.pharmacy)
        self.facility.status = 'suspended'
        self.facility.save()
        self.assertEqual(self.client.get(reverse('inventory_list')).status_code, 403)
        self.assertEqual(self.client.get(reverse('dispense_scan')).status_code, 403)

    def test_nurse_can_dispense_but_cannot_edit_stock_or_prescribe(self):
        rx, item, token = self.make_prescription()
        self.client.force_login(self.nurse)
        self.assertEqual(self.client.get(reverse('inventory_list')).status_code, 403)
        self.assertEqual(self.client.get(reverse('doctor_prescription_create')).status_code, 403)
        response = self.client.get(reverse('dispense_verify', args=[token]))
        key = response.context['form'].initial['confirmation_key']
        response = self.client.post(reverse('dispense_verify', args=[token]), {f'item_{item.pk}': 4, 'confirmation_key': key})
        self.assertRedirects(response, reverse('staff_reports'))
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 21)
        allocation = DispenseAllocation.objects.get()
        self.assertEqual((allocation.stock, allocation.quantity), (self.stock, 4))

    def test_pharmacy_combines_inventory_and_dispensing(self):
        self.client.force_login(self.pharmacy)
        for name in ('inventory_list', 'inventory_upload', 'dispense_scan', 'dashboard', 'medicine_identify'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertContains(self.client.get(reverse('dashboard')), 'Out of stock')
        self.assertContains(self.client.get(reverse('dashboard')), 'Expiring within 30 days')

    def test_duplicate_partial_submission_is_idempotent(self):
        rx, item, token = self.make_prescription()
        self.client.force_login(self.nurse)
        key = uuid.uuid4()
        data = {f'item_{item.pk}': 2, 'confirmation_key': key}
        for _ in range(2):
            self.assertEqual(self.client.post(reverse('dispense_verify', args=[token]), data).status_code, 302)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 23)
        self.assertEqual(DispenseEvent.objects.count(), 1)
        self.assertEqual(DispenseTransaction.objects.count(), 1)
        with self.assertRaises(DispenseError):
            dispense_prescription(prescription=rx, quantities={item.pk: 3}, facility=self.facility, dispenser=self.nurse, confirmation_key=key)

    def test_expired_verification_changes_no_prescription_or_stock(self):
        rx, item, token = self.make_prescription(valid_until=timezone.now() - timedelta(minutes=1))
        self.client.force_login(self.nurse)
        response = self.client.get(reverse('dispense_verify', args=[token]))
        self.assertEqual(response.status_code, 409)
        self.assertNotContains(response, 'Amoxicillin', status_code=409)
        rx.refresh_from_db()
        self.assertEqual(rx.status, Prescription.Status.ACTIVE)
        self.assertFalse(DispenseEvent.objects.exists())

    def test_cross_facility_dispense_is_denied_at_service_boundary(self):
        rx, item, _ = self.make_prescription()
        other = Facility.objects.create(name='Unassigned', status='active', facility_type='clinic', address='Elsewhere', latitude=-24, longitude=25)
        with self.assertRaises(PermissionDenied):
            dispense_prescription(prescription=rx, quantities={item.pk: 1}, facility=other, dispenser=self.nurse)

    def test_reports_scope_filters_and_exports(self):
        rx, item, token = self.make_prescription()
        rx.recipient_name = 'Private Recipient'
        rx.recipient_reference = 'PRIVATE-001'
        rx.save()
        self.client.force_login(self.nurse)
        self.client.get(reverse('dispense_verify', args=[token]))
        dispense_prescription(prescription=rx, quantities={item.pk: 1}, facility=self.facility, dispenser=self.nurse)
        other = Facility.objects.create(name='Hidden Clinic', address='Elsewhere', facility_type='clinic')
        DispenseEvent.objects.create(item=item, facility=other, quantity=1, dispensed_by=self.nurse)
        response = self.client.get(reverse('staff_reports'), {'report': 'dispensing'})
        self.assertEqual(response.context['row_count'], 1)
        self.assertNotContains(response, 'Hidden Clinic')
        self.assertNotContains(response, 'Private Recipient')
        export = self.client.get(reverse('staff_reports'), {'report': 'dispensing', 'export': 'csv'})
        self.assertContains(export, 'Amoxicillin')
        self.assertNotContains(export, 'PRIVATE-001')
        self.assertNotContains(export, 'Hidden Clinic')
        future = self.client.get(reverse('staff_reports'), {'report': 'dispensing', 'start': (timezone.localdate() + timedelta(days=1)).isoformat()})
        self.assertEqual(future.context['row_count'], 0)
        tampered = self.client.get(reverse('staff_reports'), {'report': 'dispensing', 'facility': other.pk})
        self.assertEqual(tampered.context['row_count'], 0)
        self.assertTrue(tampered.context['form'].errors)
        self.assertContains(self.client.get(reverse('staff_reports'), {'report': 'verification'}), 'Verified')

    def test_pharmacy_reports_and_csv_formula_escape(self):
        self.facility.name = '=SYNTHETIC()'
        self.facility.save()
        self.client.force_login(self.pharmacy)
        for report in ('stock', 'activity', 'dispensing', 'verification'):
            self.assertEqual(self.client.get(reverse('staff_reports'), {'report': report}).status_code, 200)
        response = self.client.get(reverse('staff_reports'), {'report': 'stock', 'export': 'csv'})
        self.assertContains(response, "'=SYNTHETIC()")
        forbidden = self.client.get(reverse('staff_reports'), {'report': 'prescriptions'})
        self.assertTrue(forbidden.context['form'].errors)

    def test_scan_requires_confirmation_before_search(self):
        self.client.force_login(self.doctor)
        response = self.client.get(reverse('medicine_identify'), {'code': self.medicine.barcode})
        self.assertContains(response, 'Confirm &amp; search stock')
        self.assertNotContains(response, 'Workflow Clinic')
        self.assertContains(self.client.get(reverse('medicine_identify'), {'code': 'unknown'}), 'No matching medicine')

    def test_batch_upload_keeps_distinct_batches(self):
        rows = [[self.medicine.code, self.medicine.name, self.medicine.strength, self.medicine.form, 3, self.stock.expiry_date, batch] for batch in ('A', 'B', 'B')]
        upload = validate_inventory_workbook(uploaded_file=workbook_upload(rows, headers=['medicine_code', 'medicine_name', 'strength', 'form', 'quantity', 'expiry_date', 'batch_number']), facility=self.facility, actor=self.pharmacy)
        self.assertEqual((upload.accepted_count, upload.rejected_count), (2, 1))
        commit_inventory_upload(upload=upload, actor=self.pharmacy)
        self.assertEqual(set(InventoryItem.objects.filter(batch_number__in=['A', 'B']).values_list('batch_number', flat=True)), {'A', 'B'})

    def test_working_facility_switch_is_authorized(self):
        other = Facility.objects.create(name='Second clinic', address='Elsewhere', facility_type='clinic', status='active', latitude=-24, longitude=25)
        self.client.force_login(self.pharmacy)
        self.assertEqual(self.client.post(reverse('select_facility'), {'facility': other.pk}).status_code, 403)
        FacilityMembership.objects.create(user=self.pharmacy, facility=other, role=User.Role.PHARMACY)
        self.assertRedirects(self.client.post(reverse('select_facility'), {'facility': other.pk}), reverse('dashboard'))
        self.assertContains(self.client.get(reverse('inventory_list')), 'Second clinic inventory')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ConcurrentDispensingTests(TransactionTestCase):
    def test_same_confirmation_in_parallel_deducts_once(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Row locking requires PostgreSQL')
        staff = User.objects.create_user('concurrent', 'concurrent@example.test', primary_role=User.Role.NURSE)
        StaffProfile.objects.create(user=staff)
        facility = Facility.objects.create(name='Concurrent clinic', address='Gaborone', status='active', latitude=-24, longitude=25)
        FacilityMembership.objects.create(user=staff, facility=facility, role=User.Role.NURSE)
        from apps.medicines.models import Medicine
        medicine = Medicine.objects.create(code='CONCURRENT', name='Synthetic', strength='1', form='test')
        stock = InventoryItem.objects.create(facility=facility, medicine=medicine, quantity=10)
        rx = Prescription.objects.create(prescriber=staff, valid_until=timezone.now() + timedelta(days=1), token_hash=token_digest('concurrent'), token_hint='test', qr_image='test.png')
        item = PrescriptionItem.objects.create(prescription=rx, medicine=medicine, dosage='test', prescribed_quantity=8)
        barrier = Barrier(2)
        key = uuid.uuid4()
        def submit():
            close_old_connections()
            try:
                actor = User.objects.get(pk=staff.pk)
                barrier.wait(timeout=10)
                dispense_prescription(prescription=rx, quantities={item.pk: 3}, facility=facility, dispenser=actor, confirmation_key=key)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [executor.submit(submit) for _ in range(2)]
            for result in results:
                result.result(timeout=20)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 7)
        self.assertEqual(DispenseEvent.objects.count(), 1)
        self.assertEqual(DispenseTransaction.objects.count(), 1)
