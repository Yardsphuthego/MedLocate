from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.dashboard.views import HomeView
from apps.accounts.views import DropdownLoginView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("accounts/login/", DropdownLoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/", include("apps.accounts.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("patient/", include("apps.search.urls")),
    path("facility/", include("apps.inventory.urls")),
    path("", include("apps.prescriptions.urls")),
    path("admin/", admin.site.urls),
]
