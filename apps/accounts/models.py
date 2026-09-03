from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        PATIENT = "patient", "Patient"
        DOCTOR = "doctor", "Doctor"
        DISPENSER = "dispenser", "Dispenser"
        INVENTORY = "inventory", "Inventory officer"
        FACILITY_ADMIN = "facility_admin", "Facility administrator"
        PLATFORM_ADMIN = "platform_admin", "Platform administrator"

    primary_role = models.CharField(max_length=24, choices=Role.choices, default=Role.PATIENT)
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.get_full_name() or self.username


class PatientProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="patient_profile")
    phone = models.CharField(max_length=20, blank=True)
    retain_search_history = models.BooleanField(default=True)
    consent_acknowledged = models.BooleanField(default=False)

    def __str__(self):
        return f"Patient: {self.user}"


class StaffProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")
    registration_reference = models.CharField(max_length=80, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return f"Staff: {self.user}"
