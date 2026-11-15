from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_alter_user_phone"),
        ("catalog", "0017_vehicle_catalogue"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerVehicle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("vehicle_type", models.CharField(choices=[("car", "Car"), ("bike", "Bike")], max_length=10)),
                ("custom_make", models.CharField(blank=True, max_length=100)),
                ("custom_model", models.CharField(blank=True, max_length=120)),
                ("nickname", models.CharField(blank=True, max_length=60)),
                ("is_default", models.BooleanField(default=False)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="saved_vehicles", to=settings.AUTH_USER_MODEL)),
                ("vehicle_model", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="customer_vehicles", to="catalog.vehiclemodel")),
            ],
            options={"ordering": ["-is_default", "-updated_at"]},
        ),
        migrations.AddConstraint(
            model_name="customervehicle",
            constraint=models.UniqueConstraint(condition=models.Q(("is_default", True)), fields=("user",), name="one_default_vehicle_per_customer"),
        ),
    ]
