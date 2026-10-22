from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import CreateView

from apps.audit.services import record_event
from apps.facilities.models import FacilityMembership
from .forms import AdminUserCreationForm
from .models import PatientProfile, StaffProfile, User


class DropdownLoginView(LoginView):
    """Keep account access in the header dropdown rather than a separate page."""

    def _dropdown_url(self):
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        query = f"?{urlencode({'next': next_url})}" if next_url else ""
        return f"{reverse('home')}{query}#sign-in"

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return redirect(self._dropdown_url())

    def form_valid(self, form):
        if form.get_user().primary_role == User.Role.PATIENT and not form.get_user().is_superuser:
            messages.error(self.request, "MedLocate is now a staff platform. Contact your facility administrator for access.")
            return redirect(self._dropdown_url())
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "The username or password was not recognized. Please try again.")
        return redirect(self._dropdown_url())


def register(request):
    from django.http import HttpResponseGone
    return HttpResponseGone("Public registration is closed. Ask your facility administrator for an approved staff account.")


class AdminUserCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    form_class = AdminUserCreationForm
    template_name = "accounts/admin_user_form.html"

    def test_func(self):
        return self.request.user.is_active and self.request.user.is_superuser

    @transaction.atomic
    def form_valid(self, form):
        account = form.save()
        facility = form.cleaned_data["facility"]
        if account.primary_role == User.Role.PATIENT:
            PatientProfile.objects.create(user=account)
        else:
            StaffProfile.objects.create(user=account)
        if facility:
            FacilityMembership.objects.create(user=account, facility=facility, role=account.primary_role)
        record_event(
            actor=self.request.user, action="account.created", obj=account, facility=facility,
            metadata={"role": account.primary_role},
        )
        messages.success(self.request, f"User {account.username} created successfully.")
        return redirect("dashboard")


from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .access import CLINICAL_ROLES, require_membership


@login_required
@require_POST
def select_facility(request):
    value = request.POST.get("facility", "")
    if not value.isdecimal():
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    membership = require_membership(request.user, CLINICAL_ROLES, int(value))
    request.session["active_facility"] = membership.facility_id
    return redirect("dashboard")
