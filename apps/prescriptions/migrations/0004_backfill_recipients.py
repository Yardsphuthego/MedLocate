from django.db import migrations


def backfill(apps, schema_editor):
    Prescription = apps.get_model('prescriptions', 'Prescription')
    for prescription in Prescription.objects.select_related('patient').filter(patient__isnull=False, recipient_name=''):
        patient = prescription.patient
        prescription.recipient_name = f'{patient.first_name} {patient.last_name}'.strip() or patient.username
        prescription.recipient_reference = f'LEGACY-{patient.pk}'
        prescription.save(update_fields=['recipient_name', 'recipient_reference'])


class Migration(migrations.Migration):
    dependencies = [('prescriptions', '0003_dispenseallocation')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
