from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_zone_coverage_radius"),
    ]

    operations = [
        migrations.AddField(
            model_name="zone",
            name="coverage_polygon",
            field=models.JSONField(
                blank=True,
                help_text='GeoJSON Polygon geometry: {"type": "Polygon", "coordinates": [[[longitude, latitude], ...]]}.',
                null=True,
            ),
        ),
    ]
