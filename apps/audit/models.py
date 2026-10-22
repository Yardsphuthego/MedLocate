from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80, db_index=True)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80, blank=True)
    facility = models.ForeignKey("facilities.Facility", null=True, blank=True, on_delete=models.SET_NULL)
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-timestamp",)

    @property
    def action_label(self):
        labels = {
            "account.created": "Account created",
            "inventory.updated": "Stock updated",
            "inventory.upload_validated": "Inventory upload validated",
            "inventory.upload_committed": "Inventory import committed",
            "prescription.created": "Prescription issued",
            "prescription.verified": "Prescription verified",
            "prescription.dispensed": "Medicine dispensed",
            "prescription.cancelled": "Prescription cancelled",
            "verification.rejected": "Verification rejected",
            "dispensing.rejected": "Dispensing rejected",
        }
        return labels.get(self.action, self.action.replace(".", " ").replace("_", " ").capitalize())

    def delete(self, *args, **kwargs):
        raise TypeError("Audit events are append-only.")
