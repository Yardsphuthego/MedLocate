from django.urls import path
from .views import AdminUserCreateView, register, select_facility

urlpatterns = [
    path("facility/", select_facility, name="select_facility"),
    path("register/", register, name="register"),
    path("users/new/", AdminUserCreateView.as_view(), name="admin_user_create"),
]
