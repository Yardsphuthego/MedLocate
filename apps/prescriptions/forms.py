from django import forms
from django.forms import formset_factory
from django.utils import timezone
from apps.accounts.models import User
from apps.medicines.models import Medicine
from .models import Prescription


class PrescriptionForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = ("patient", "valid_until", "notes")
        widgets = {"valid_until": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = User.objects.filter(primary_role=User.Role.PATIENT, is_active=True).order_by("first_name", "last_name")
        self.fields["valid_until"].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean_valid_until(self):
        value = self.cleaned_data["valid_until"]
        if value <= timezone.now():
            raise forms.ValidationError("Expiry must be in the future.")
        return value


class PrescriptionItemForm(forms.Form):
    medicine = forms.ModelChoiceField(queryset=Medicine.objects.filter(active=True))
    dosage = forms.CharField(max_length=160, help_text="Clinical directions entered by the authorized prescriber.")
    prescribed_quantity = forms.IntegerField(min_value=1)
    instructions = forms.CharField(max_length=255, required=False)


PrescriptionItemFormSet = formset_factory(PrescriptionItemForm, extra=3, min_num=1, validate_min=True)


class TokenScanForm(forms.Form):
    token = forms.CharField(max_length=500, label="Prescription token or QR link")

    def clean_token(self):
        value = self.cleaned_data["token"].strip().rstrip("/")
        if "/dispense/verify/" in value:
            value = value.rsplit("/", 1)[-1]
        if len(value) < 32:
            raise forms.ValidationError("This prescription token is not valid.")
        return value


class DispenseForm(forms.Form):
    def __init__(self, *args, items, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = list(items)
        for item in self.items:
            self.fields[f"item_{item.pk}"] = forms.IntegerField(
                min_value=0, max_value=item.remaining_quantity, initial=0,
                label=f"{item.medicine} — remaining {item.remaining_quantity}",
            )

    def clean(self):
        cleaned = super().clean()
        if not self.errors and not any(cleaned.get(f"item_{item.pk}", 0) for item in self.items):
            raise forms.ValidationError("Enter a quantity for at least one prescription item.")
        return cleaned

    def quantities(self):
        return {item.pk: self.cleaned_data[f"item_{item.pk}"] for item in self.items if self.cleaned_data[f"item_{item.pk}"] > 0}
