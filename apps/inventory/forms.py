from django import forms
from .models import InventoryItem


class InventoryUploadForm(forms.Form):
    workbook = forms.FileField(help_text="Use the MedLocate .xlsx template. Maximum size is set by the project configuration.")

    def clean_workbook(self):
        from django.conf import settings

        workbook = self.cleaned_data["workbook"]
        if not workbook.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Upload an .xlsx workbook.")
        if workbook.size > settings.MAX_INVENTORY_UPLOAD_BYTES:
            raise forms.ValidationError("The workbook exceeds the configured upload size limit.")
        return workbook


class InventoryItemForm(forms.ModelForm):
    reason = forms.CharField(max_length=255, help_text="Required for the audit history.")

    class Meta:
        model = InventoryItem
        fields = ("medicine", "batch_number", "quantity", "expiry_date", "low_stock_threshold")
        widgets = {"expiry_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, facility=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.facility = facility

    def clean(self):
        cleaned = super().clean()
        expiry = cleaned.get("expiry_date")
        if expiry and expiry < __import__("datetime").date.today() and cleaned.get("quantity", 0) > 0:
            self.add_error("expiry_date", "Expired medicine cannot be recorded as available stock.")
        medicine = cleaned.get("medicine")
        if self.facility and medicine:
            duplicate = InventoryItem.objects.filter(
                facility=self.facility, medicine=medicine, batch_number=cleaned.get("batch_number", ""), expiry_date=expiry
            ).exclude(pk=self.instance.pk)
            if duplicate.exists():
                self.add_error("medicine", "This facility already has a stock record for this medicine and expiry date.")
        return cleaned
