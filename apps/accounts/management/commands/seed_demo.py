from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.accounts.models import PatientProfile, StaffProfile, User
from apps.facilities.models import Facility, FacilityMembership
from apps.inventory.models import InventoryItem
from apps.medicines.models import Medicine, MedicineAlias


class Command(BaseCommand):
    help = "Create synthetic MedLocate demonstration accounts and stock."

    @transaction.atomic
    def handle(self, *args, **options):
        facilities = [
            ("Gaborone Central Clinic", "clinic", "Central Gaborone", -24.6581, 25.9122),
            ("Block 8 Community Clinic", "clinic", "Block 8, Gaborone", -24.6047, 25.9252),
            ("Princess Marina Hospital", "hospital", "Independence Avenue, Gaborone", -24.6543, 25.9194),
        ]
        facility_objects = []
        for name, kind, address, lat, lon in facilities:
            facility, _ = Facility.objects.update_or_create(name=name, defaults={
                "facility_type": kind, "address": address, "latitude": lat,
                "longitude": lon, "status": Facility.Status.ACTIVE,
            })
            facility_objects.append(facility)

        medicines = [
            ("MED-PAR-500", "Paracetamol", "Acetaminophen", "500 mg", "tablet", "600100000001"),
            ("MED-AMX-500", "Amoxicillin", "Amoxicillin", "500 mg", "capsule", "600100000002"),
            ("MED-ORS-001", "Oral rehydration salts", "ORS", "20.5 g", "sachet", "600100000003"),
        ]
        medicine_objects = []
        for code, name, generic, strength, form, barcode in medicines:
            medicine, _ = Medicine.objects.update_or_create(code=code, defaults={
                "name": name, "generic_name": generic, "strength": strength,
                "form": form, "barcode": barcode, "active": True,
            })
            medicine_objects.append(medicine)
        MedicineAlias.objects.get_or_create(medicine=medicine_objects[0], name="Panado")

        for facility_index, facility in enumerate(facility_objects):
            for medicine_index, medicine in enumerate(medicine_objects):
                InventoryItem.objects.update_or_create(
                    facility=facility, medicine=medicine, expiry_date=date.today() + timedelta(days=180 + medicine_index * 30),
                    defaults={"quantity": 18 + facility_index * 12 + medicine_index * 7, "low_stock_threshold": 10},
                )

        patient, created = User.objects.get_or_create(username="demo.patient", defaults={
            "email": "patient@example.test", "first_name": "Demo", "last_name": "Patient", "primary_role": User.Role.PATIENT,
        })
        patient.email = "patient@example.test"
        patient.primary_role = User.Role.PATIENT
        patient.set_password("DemoPatient2026!")
        patient.save()
        PatientProfile.objects.get_or_create(user=patient, defaults={"phone": "+267 71000001", "consent_acknowledged": True})

        inventory_user, _ = User.objects.get_or_create(username="demo.inventory", defaults={
            "email": "inventory@example.test", "first_name": "Demo", "last_name": "Officer", "primary_role": User.Role.INVENTORY,
        })
        inventory_user.email = "inventory@example.test"
        inventory_user.primary_role = User.Role.INVENTORY
        inventory_user.set_password("DemoInventory2026!")
        inventory_user.save()
        StaffProfile.objects.get_or_create(user=inventory_user)
        FacilityMembership.objects.get_or_create(
            user=inventory_user, facility=facility_objects[0], role=User.Role.INVENTORY,
            defaults={"active": True},
        )
        doctor, _ = User.objects.get_or_create(username="demo.doctor", defaults={
            "email": "doctor@example.test", "first_name": "Demo", "last_name": "Doctor", "primary_role": User.Role.DOCTOR,
        })
        doctor.email = "doctor@example.test"
        doctor.primary_role = User.Role.DOCTOR
        doctor.set_password("DemoDoctor2026!")
        doctor.save()
        StaffProfile.objects.get_or_create(user=doctor, defaults={"registration_reference": "SYNTH-DR-001"})

        dispenser, _ = User.objects.get_or_create(username="demo.dispenser", defaults={
            "email": "dispenser@example.test", "first_name": "Demo", "last_name": "Dispenser", "primary_role": User.Role.DISPENSER,
        })
        dispenser.email = "dispenser@example.test"
        dispenser.primary_role = User.Role.DISPENSER
        dispenser.set_password("DemoDispenser2026!")
        dispenser.save()
        StaffProfile.objects.get_or_create(user=dispenser, defaults={"registration_reference": "SYNTH-DSP-001"})
        FacilityMembership.objects.get_or_create(
            user=dispenser, facility=facility_objects[0], role=User.Role.DISPENSER,
            defaults={"active": True},
        )
        self.stdout.write(self.style.SUCCESS("Synthetic demo data ready."))
        self.stdout.write("Patient: demo.patient / DemoPatient2026!")
        self.stdout.write("Inventory: demo.inventory / DemoInventory2026!")
        self.stdout.write("Doctor: demo.doctor / DemoDoctor2026!")
        self.stdout.write("Dispenser: demo.dispenser / DemoDispenser2026!")
