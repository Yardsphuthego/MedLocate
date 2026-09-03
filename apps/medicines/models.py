from django.db import models


class Medicine(models.Model):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=160, db_index=True)
    generic_name = models.CharField(max_length=160, blank=True, db_index=True)
    strength = models.CharField(max_length=80)
    form = models.CharField(max_length=60)
    barcode = models.CharField(max_length=80, blank=True, unique=True, null=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name", "strength")

    def __str__(self):
        return f"{self.name} {self.strength} ({self.form})"


class MedicineAlias(models.Model):
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name="aliases")
    name = models.CharField(max_length=160, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("medicine", "name"), name="unique_medicine_alias")]

    def __str__(self):
        return self.name
