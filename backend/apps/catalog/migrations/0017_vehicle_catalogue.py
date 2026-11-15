from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0016_formfield_date_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="VehicleMake",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("vehicle_type", models.CharField(choices=[("car", "Car"), ("bike", "Bike")], max_length=10)),
                ("name", models.CharField(max_length=100)),
                ("logo", models.ImageField(blank=True, upload_to="vehicle_makes/")),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["sort_order", "name"]},
        ),
        migrations.CreateModel(
            name="VehicleModel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("image", models.ImageField(blank=True, upload_to="vehicle_models/")),
                ("vehicle_class", models.CharField(blank=True, help_text="Optional pricing class used by car-wash packages, e.g. Hatchback, Sedan, SUV.", max_length=30)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("make", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="models", to="catalog.vehiclemake")),
            ],
            options={"ordering": ["sort_order", "name"]},
        ),
        migrations.AddConstraint(
            model_name="vehiclemake",
            constraint=models.UniqueConstraint(fields=("vehicle_type", "name"), name="unique_vehicle_make_type_name"),
        ),
        migrations.AddConstraint(
            model_name="vehiclemodel",
            constraint=models.UniqueConstraint(fields=("make", "name"), name="unique_vehicle_model_per_make"),
        ),
    ]
