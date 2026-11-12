from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_zone_latitude_zone_longitude"),
    ]

    operations = [
        migrations.AddField(
            model_name="zone",
            name="coverage_radius_meters",
            field=models.PositiveIntegerField(
                default=5000,
                help_text="Maximum GPS distance from this zone centre for automatic worker zone assignment.",
            ),
        ),
    ]
