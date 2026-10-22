from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from apps.accounts.models import User


class Facility(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    class Type(models.TextChoices):
        CLINIC = "clinic", "Clinic"
        HOSPITAL = "hospital", "Hospital"
        PHARMACY = "pharmacy", "Approved pharmacy"

    name = models.CharField(max_length=160, unique=True)
    facility_type = models.CharField(max_length=20, choices=Type.choices)
    address = models.CharField(max_length=255)
    phone = models.CharField(max_length=30, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        verbose_name_plural = "Facilities"

    def clean(self):
        if self.status == self.Status.ACTIVE and (self.latitude is None or self.longitude is None):
            raise ValidationError("An active facility must have latitude and longitude.")

    def __str__(self):
        return self.name


class FacilityMembership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="facility_memberships")
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=24, choices=User.Role.choices)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "facility", "role"), name="unique_facility_membership")]

    def __str__(self):
        return f"{self.user} — {self.facility} ({self.get_role_display()})"
