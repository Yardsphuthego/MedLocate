from datetime import timedelta
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class InventoryItem(models.Model):
    facility = models.ForeignKey("facilities.Facility", on_delete=models.CASCADE, related_name="inventory")
    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="inventory")
    batch_number = models.CharField(max_length=80, blank=True)
    quantity = models.PositiveIntegerField(default=0)
    expiry_date = models.DateField(null=True, blank=True)
    low_stock_threshold = models.PositiveIntegerField(default=10)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("facility", "medicine", "batch_number", "expiry_date"), name="unique_inventory_batch"),
                       models.UniqueConstraint(fields=("facility", "medicine", "batch_number"), condition=models.Q(expiry_date__isnull=True), name="unique_undated_inventory_batch")]
        ordering = ("medicine__name",)

    @property
    def freshness(self):
        age = timezone.now() - self.updated_at
        if age <= timedelta(hours=settings.STOCK_FRESH_HOURS):
            return "fresh"
        if age <= timedelta(hours=settings.STOCK_STALE_HOURS):
            return "aging"
        return "stale"

    @property
    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < timezone.localdate())

    def __str__(self):
        return f"{self.facility}: {self.medicine} × {self.quantity}"


class InventoryAdjustment(models.Model):
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="adjustments")
    previous_quantity = models.PositiveIntegerField()
    new_quantity = models.PositiveIntegerField(validators=[MinValueValidator(0)])
    reason = models.CharField(max_length=255)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class InventoryUpload(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        VALIDATED = "validated", "Validated"
        REJECTED = "rejected", "Rejected"
        IMPORTED = "imported", "Imported"

    facility = models.ForeignKey("facilities.Facility", on_delete=models.PROTECT, related_name="inventory_uploads")
    original_name = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)
    accepted_count = models.PositiveIntegerField(default=0)
    rejected_count = models.PositiveIntegerField(default=0)
    parsed_rows = models.JSONField(default=list, blank=True)
    error_text = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    committed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)


class InventoryUploadRow(models.Model):
    class Status(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    upload = models.ForeignKey(InventoryUpload, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices)
    error_text = models.TextField(blank=True)
    normalized_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("row_number",)
        constraints = [models.UniqueConstraint(fields=("upload", "row_number"), name="unique_upload_row_number")]
