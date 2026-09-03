from django.urls import path
from . import views

urlpatterns = [
    path("inventory/", views.inventory_list, name="inventory_list"),
    path("inventory/new/", views.inventory_edit, name="inventory_create"),
    path("inventory/<int:pk>/edit/", views.inventory_edit, name="inventory_edit"),
    path("inventory/upload/", views.inventory_upload, name="inventory_upload"),
    path("inventory/upload/<int:pk>/", views.inventory_upload_preview, name="inventory_upload_preview"),
    path("inventory/template/", views.inventory_template, name="inventory_template"),
]
