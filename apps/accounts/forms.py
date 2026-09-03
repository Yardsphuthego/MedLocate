from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User


class PatientRegistrationForm(UserCreationForm):
    email = forms.EmailField()
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    phone = forms.CharField(max_length=20, help_text="Use a Botswana number where possible (for example, +267 71 234 567).")
    consent_acknowledged = forms.BooleanField(
        label="I agree to MedLocate's privacy and account terms."
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "phone", "password1", "password2", "consent_acknowledged")
