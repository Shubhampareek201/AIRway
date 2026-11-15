from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0019_seed_premium_vehicle_makes"),
    ]

    operations = [
        migrations.AddField(
            model_name="vehiclemodel",
            name="image_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="vehiclemake",
            name="logo_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
    ]
