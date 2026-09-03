from django.conf import settings
from django.db import models


class SearchHistory(models.Model):
    class QueryType(models.TextChoices):
        TEXT = "text", "Text"
        BARCODE = "barcode", "Barcode"
        OCR = "ocr", "OCR"

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="search_history")
    query = models.CharField(max_length=160)
    query_type = models.CharField(max_length=12, choices=QueryType.choices, default=QueryType.TEXT)
    medicine = models.ForeignKey("medicines.Medicine", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
