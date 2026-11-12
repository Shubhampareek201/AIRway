from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workers", "0005_worker_service_experience_and_aadhaar_sides"),
    ]

    operations = [
        migrations.AddField(
            model_name="workerprofile",
            name="latitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="workerprofile",
            name="longitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
    ]
