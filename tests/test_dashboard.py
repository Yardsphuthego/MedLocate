from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.facilities.models import Facility, FacilityMembership
from apps.inventory.models import InventoryItem
from tests.test_core import CoreFixture


class PlatformDashboardTests(CoreFixture):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser('dashboard-admin', 'dashboard@example.test', 'test-password')
        self.client.force_login(self.admin)

    def test_facility_totals_are_not_multiplied_by_memberships_or_equal_batches(self):
        FacilityMembership.objects.create(user=self.officer, facility=self.facility, role=User.Role.FACILITY_ADMIN)
        FacilityMembership.objects.create(user=self.patient, facility=self.facility, role=User.Role.DOCTOR, active=False)
        InventoryItem.objects.create(facility=self.facility, medicine=self.medicine, quantity=25,
                                     expiry_date=timezone.localdate() + timedelta(days=180))
        response = self.client.get(reverse('dashboard'))
        row = next(row for row in response.context['facility_rows'] if row.pk == self.facility.pk)
        self.assertEqual((row.total_units, row.stock_records, row.staff_count), (50, 2, 1))
        self.assertNotIn(self.patient, response.context['recent_users'])
        self.assertEqual(response.context['metrics'][0]['value'], 2)

    def test_facility_search_status_and_pagination(self):
        for n in range(10):
            Facility.objects.create(name=f'Draft {n:02}', address='Francistown', facility_type=Facility.Type.CLINIC)
        response = self.client.get(reverse('dashboard'), {'q': 'Francistown', 'status': 'draft', 'page': 2})
        self.assertEqual(response.context['facility_page'].paginator.count, 10)
        self.assertEqual(len(response.context['facility_rows']), 2)
        self.assertContains(response, 'q=Francistown&amp;status=draft')
        self.assertNotContains(response, 'Other Clinic')
        empty = self.client.get(reverse('dashboard'), {'q': 'missing'})
        self.assertContains(empty, 'No facilities match these filters')
        self.assertEqual(self.client.get(reverse('dashboard'), {'page': 'invalid', 'status': 'invalid', 'health': 'invalid'}).status_code, 200)

    def test_alert_counts_and_details_agree(self):
        InventoryItem.objects.filter(pk=self.item.pk).update(
            quantity=0, expiry_date=timezone.localdate() - timedelta(days=1),
            updated_at=timezone.now() - timedelta(hours=settings.STOCK_STALE_HOURS + 1),
        )
        for category in ('low', 'stale', 'expired', 'zero'):
            response = self.client.get(reverse('dashboard'), {'health': category})
            self.assertEqual([item.pk for item in response.context['health_page']], [self.item.pk])
            alert = next(alert for alert in response.context['health_alerts'] if alert['key'] == category)
            self.assertEqual(alert['count'], 1)
            self.assertContains(response, 'aria-current="true"')

    def test_admin_controls_resolve_and_are_accessible(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(len(response.context['quick_actions']), 9)
        for action in response.context['quick_actions']:
            self.assertEqual(self.client.get(action['url']).status_code, 200)

    def test_admin_tabs_stay_in_workspace_and_only_frame_same_origin_admin(self):
        target = reverse('admin:accounts_user_changelist')
        workspace = self.client.get(reverse('admin_workspace'), {'view': target})
        self.assertContains(workspace, f'src="{target}"')
        self.assertContains(workspace, 'med-workspace-nav')
        direct_admin = self.client.get(target)
        self.assertEqual(direct_admin['X-Frame-Options'], 'SAMEORIGIN')
        self.assertContains(direct_admin, 'med-workspace-header')
        self.assertNotContains(direct_admin, 'id="nav-sidebar"')
        self.assertEqual(self.client.get(reverse('admin_workspace'), {'view': 'https://example.com/'}).status_code, 404)
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(reverse('admin_workspace'), {'view': target}).status_code, 403)

    def test_platform_role_does_not_grant_django_admin_permissions(self):
        self.patient.primary_role = User.Role.PLATFORM_ADMIN
        self.patient.save()
        self.client.force_login(self.patient)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, '<h1>Operations</h1>', html=True)
        self.assertEqual(response.context['quick_actions'], [])
        self.assertNotContains(response, 'Open Django administration')
        self.assertNotContains(response, reverse('admin:facilities_facility_change', args=[self.facility.pk]))

    def test_patient_cannot_open_platform_data_with_filters(self):
        self.client.force_login(self.patient)
        response = self.client.get(reverse('dashboard'), {'health': 'low', 'q': 'Other'})
        self.assertEqual(response.status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)


class OperationalDashboardTests(CoreFixture):
    def test_inventory_worklist_and_stock_preview_stay_within_assigned_facilities(self):
        InventoryItem.objects.create(
            facility=self.other_facility, medicine=self.medicine, quantity=40,
            expiry_date=timezone.localdate() + timedelta(days=90),
        )
        self.item.quantity = 3
        self.item.save()
        self.client.force_login(self.officer)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Stock requiring review')
        self.assertEqual([item.pk for item in response.context['stock_preview']], [self.item.pk])
        self.assertTrue(any(row['title'] == self.medicine.name and row['status'] == 'Low stock' for row in response.context['focus_rows']))
        self.assertNotContains(response, self.other_facility.name)
        self.item.quantity = 0
        self.item.save()
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(list(response.context['stock_preview']), [])
