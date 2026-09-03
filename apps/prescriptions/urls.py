from django.urls import path
from . import views

urlpatterns = [
    path("doctor/prescriptions/", views.doctor_prescription_list, name="doctor_prescription_list"),
    path("doctor/prescriptions/new/", views.doctor_prescription_create, name="doctor_prescription_create"),
    path("doctor/prescriptions/<int:pk>/", views.doctor_prescription_detail, name="doctor_prescription_detail"),
    path("doctor/prescriptions/<int:pk>/cancel/", views.doctor_prescription_cancel, name="doctor_prescription_cancel"),
    path("patient/prescriptions/", views.patient_prescription_list, name="patient_prescription_list"),
    path("patient/prescriptions/<int:pk>/", views.patient_prescription_detail, name="patient_prescription_detail"),
    path("prescriptions/<int:pk>/qr/", views.prescription_qr, name="prescription_qr"),
    path("dispense/scan/", views.dispense_scan, name="dispense_scan"),
    path("dispense/verify/<str:token>/", views.dispense_verify, name="dispense_verify"),
]
