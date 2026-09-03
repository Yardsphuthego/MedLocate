from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView, View
from apps.accounts.models import User


class HomeView(TemplateView):
    template_name = "home.html"


class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.primary_role == User.Role.PATIENT:
            return redirect("medicine_search")
        if request.user.primary_role in {User.Role.INVENTORY, User.Role.FACILITY_ADMIN}:
            return redirect("inventory_list")
        if request.user.primary_role == User.Role.DOCTOR:
            return redirect("doctor_prescription_list")
        if request.user.primary_role == User.Role.DISPENSER:
            return redirect("dispense_scan")
        if request.user.primary_role == User.Role.PLATFORM_ADMIN and request.user.is_staff:
            return redirect("admin:index")
        return TemplateView.as_view(template_name="dashboard/role_home.html")(request)
