# Generated for complete worker onboarding details.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workers", "0002_workerjobstreak"),
    ]

    operations = [
        migrations.AddField(
            model_name="workerprofile",
            name="qualification",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="workerprofile",
            name="equipment_details",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="workerprofile",
            name="residential_address",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="workerprofile",
            name="landmark",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="workerdocument",
            name="doc_type",
            field=models.CharField(
                choices=[
                    ("aadhaar", "Aadhaar"),
                    ("id", "Other ID"),
                    ("photo", "Photograph"),
                    ("address_proof", "Address proof"),
                    ("qualification", "Qualification certificate"),
                    ("other", "Other"),
                ],
                max_length=20,
            ),
        ),
    ]
