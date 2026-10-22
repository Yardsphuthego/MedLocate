from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User


class AdminUserCreationForm(UserCreationForm):
    email = forms.EmailField()
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    facility = forms.ModelChoiceField(
        queryset=None, required=False,
        help_text="Required for doctors, nurses, pharmacy staff and facility administrators.",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "primary_role", "facility", "password1", "password2")
        help_texts = {
            "primary_role": "Platform administrators can view the platform dashboard. Django administration permissions are assigned separately.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.facilities.models import Facility
        self.fields["facility"].queryset = Facility.objects.filter(status=Facility.Status.ACTIVE).order_by("name")
        self.fields["primary_role"].label = "Role"
        self.fields["primary_role"].choices = [(value, label) for value, label in User.Role.choices if value not in {User.Role.PATIENT, User.Role.DISPENSER, User.Role.INVENTORY}]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account already uses this email address.")
        return email

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("primary_role")
        facility = cleaned.get("facility")
        staff_roles = {User.Role.DOCTOR, User.Role.NURSE, User.Role.PHARMACY, User.Role.FACILITY_ADMIN}
        if role in staff_roles and not facility:
            self.add_error("facility", "Choose an active facility for this staff account.")
        elif role in {User.Role.PATIENT, User.Role.PLATFORM_ADMIN} and facility:
            self.add_error("facility", "This role does not need a facility assignment.")
        return cleaned
