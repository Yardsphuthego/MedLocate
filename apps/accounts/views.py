from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from urllib.parse import urlencode
from .forms import PatientRegistrationForm
from .models import PatientProfile, User


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

    def form_invalid(self, form):
        messages.error(self.request, "The username or password was not recognized. Please try again.")
        return redirect(self._dropdown_url())


@transaction.atomic
def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method != "POST":
        return redirect(f"{reverse('home')}#register")
    form = PatientRegistrationForm(request.POST)
    if form.is_valid():
        user = form.save(commit=False)
        user.primary_role = User.Role.PATIENT
        user.save()
        PatientProfile.objects.create(
            user=user,
            phone=form.cleaned_data["phone"],
            consent_acknowledged=form.cleaned_data["consent_acknowledged"],
        )
        login(request, user)
        messages.success(request, "Your patient account is ready.")
        return redirect("medicine_search")
    for field_name, errors in form.errors.items():
        label = form.fields[field_name].label if field_name in form.fields else "Account"
        for error in errors:
            messages.error(request, f"{label}: {error}")
    return redirect(f"{reverse('home')}#register")
