from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_customer_vehicle"),
    ]

    operations = [
        migrations.AddField(
            model_name="customervehicle",
            name="vehicle_class",
            field=models.CharField(blank=True, max_length=40),
        ),
    ]
