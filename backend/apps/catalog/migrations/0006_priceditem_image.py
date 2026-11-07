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
    ]
