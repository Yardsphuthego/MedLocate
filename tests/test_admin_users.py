from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import PatientProfile, StaffProfile, User
from apps.audit.models import AuditEvent
from apps.facilities.models import Facility, FacilityMembership


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AdminUserCreationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('creator', 'creator@example.test', 'password')
        self.client.force_login(self.admin)
        self.url = reverse('admin_user_create')
        self.facility = Facility.objects.create(name='Active clinic', facility_type='clinic', address='Gaborone', status='active', latitude=-24.65, longitude=25.91)
        self.data = {
            'username': 'new.user', 'email': 'NEW@example.test', 'first_name': 'New', 'last_name': 'User',
            'primary_role': 'nurse', 'facility': self.facility.pk, 'password1': 'Secure-Account-4938!', 'password2': 'Secure-Account-4938!',
        }

    def test_form_and_staff_creation_preserve_admin_session(self):
        self.assertContains(self.client.get(self.url), 'User details')
        response = self.client.post(self.url, self.data)
        self.assertRedirects(response, reverse('dashboard'))
        user = User.objects.get(username='new.user')
        self.assertEqual(user.email, 'new@example.test')
        self.assertTrue(user.check_password(self.data['password1']))
        self.assertFalse(user.is_superuser or user.is_staff)
        self.assertTrue(StaffProfile.objects.get(user=user).active)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.admin.pk)
        event = AuditEvent.objects.get(action='account.created')
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.object_id, str(user.pk))
        self.assertNotIn('password', str(event.metadata))

    def test_staff_roles_receive_profiles_and_memberships(self):
        for role in ('doctor', 'nurse', 'pharmacy', 'facility_admin'):
            data = {**self.data, 'username': role, 'email': f'{role}@example.test', 'primary_role': role, 'facility': self.facility.pk}
            self.assertEqual(self.client.post(self.url, data).status_code, 302)
            user = User.objects.get(username=role)
            self.assertTrue(StaffProfile.objects.get(user=user).active)
            self.assertTrue(FacilityMembership.objects.filter(user=user, facility=self.facility, role=role, active=True).exists())

    def test_missing_or_inactive_facility_is_rejected(self):
        data = {**self.data, 'primary_role': 'doctor', 'facility': ''}
        self.assertContains(self.client.post(self.url, data), 'Choose an active facility')
        self.facility.status = 'suspended'
        self.facility.save()
        self.assertContains(self.client.post(self.url, {**data, 'facility': self.facility.pk}), 'Select a valid choice')
        self.assertFalse(User.objects.filter(username='new.user').exists())

    def test_duplicate_email_and_invalid_password_are_rejected(self):
        self.assertContains(self.client.post(self.url, {**self.data, 'email': 'CREATOR@example.test'}), 'already uses this email')
        self.assertEqual(self.client.post(self.url, {**self.data, 'password2': 'mismatch'}).status_code, 200)
        self.assertFalse(User.objects.filter(username='new.user').exists())

    def test_non_superusers_cannot_create_accounts(self):
        for role in User.Role.values:
            user = User.objects.create_user(role, f'{role}@example.test', 'password', primary_role=role, is_staff=True)
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.post(self.url, self.data).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, self.data).status_code, 302)
        self.assertFalse(User.objects.filter(username='new.user').exists())

    def test_platform_role_does_not_grant_superuser_flags(self):
        self.client.post(self.url, {**self.data, 'primary_role': 'platform_admin', 'facility': '', 'is_superuser': 'on', 'is_staff': 'on'})
        user = User.objects.get(username='new.user')
        self.assertFalse(user.is_superuser or user.is_staff)

    def test_failure_rolls_back_account_and_profile(self):
        with patch('apps.accounts.views.record_event', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, self.data)
        self.assertFalse(User.objects.filter(username='new.user').exists())
        self.assertFalse(PatientProfile.objects.exists())
