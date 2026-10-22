from django.urls import path
from .views import DashboardView
from .reports import staff_reports
from .views import admin_workspace

urlpatterns = [path("manage/", admin_workspace, name="admin_workspace"), path("reports/", staff_reports, name="staff_reports"), path("", DashboardView.as_view(), name="dashboard")]
