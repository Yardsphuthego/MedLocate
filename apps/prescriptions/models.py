import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Prescription(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PARTIAL = "partially_dispensed", "Partially dispensed"
        DISPENSED = "dispensed", "Dispensed"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="patient_prescriptions")
    prescriber = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="issued_prescriptions")
    issued_at = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    token_hint = models.CharField(max_length=8, editable=False)
    qr_image = models.ImageField(upload_to="qr/%Y/%m", editable=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-issued_at",)

    def clean(self):
        if self.valid_until and self.issued_at and self.valid_until <= self.issued_at:
            raise ValidationError({"valid_until": "Prescription expiry must be after its issue time."})

    @property
    def is_usable(self):
        return self.status in {self.Status.ACTIVE, self.Status.PARTIAL} and self.valid_until > timezone.now()

    def __str__(self):
        return f"Prescription {str(self.uuid)[:8]} for {self.patient}"


class PrescriptionItem(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PARTIAL = "partial", "Partial"
        FULFILLED = "fulfilled", "Fulfilled"

    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name="items")
    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT)
    dosage = models.CharField(max_length=160)
    instructions = models.CharField(max_length=255, blank=True)
    prescribed_quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    dispensed_quantity = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("prescription", "medicine"), name="unique_prescription_medicine"),
            models.CheckConstraint(condition=models.Q(dispensed_quantity__lte=models.F("prescribed_quantity")), name="dispensed_not_above_prescribed"),
        ]

    @property
    def remaining_quantity(self):
        return self.prescribed_quantity - self.dispensed_quantity

    def __str__(self):
        return f"{self.medicine} × {self.prescribed_quantity}"


class DispenseEvent(models.Model):
    item = models.ForeignKey(PrescriptionItem, on_delete=models.PROTECT, related_name="dispense_events")
    facility = models.ForeignKey("facilities.Facility", on_delete=models.PROTECT, related_name="dispense_events")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    dispensed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("timestamp",)
