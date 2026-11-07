from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0005_servicevariant_attributes"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicevariant",
            name="image",
            field=models.ImageField(blank=True, upload_to="catalog_options/"),
        ),
        migrations.AddField(
            model_name="addon",
            name="image",
            field=models.ImageField(blank=True, upload_to="catalog_options/"),
        ),
        # Keep simple-history tables aligned with the current model fields.
        migrations.AddField(
            model_name="historicalservicevariant",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="historicalservicevariant",
            name="attributes",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="historicalservicevariant",
            name="image",
            field=models.TextField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="historicaladdon",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="historicaladdon",
            name="image",
            field=models.TextField(blank=True, max_length=100),
        ),
    ]
