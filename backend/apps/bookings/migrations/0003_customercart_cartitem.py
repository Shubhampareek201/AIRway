# Generated for AIRway customer cart.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0002_workeroffer"),
        ("accounts", "0003_alter_user_phone"),
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerCart",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("address", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="customer_carts", to="accounts.address")),
                ("customer", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="service_cart", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="CartItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("addon_selections", models.JSONField(blank=True, default=list)),
                ("form_answers", models.JSONField(blank=True, default=dict)),
                ("notes", models.TextField(blank=True)),
                ("pricing_snapshot", models.JSONField(blank=True, default=dict)),
                ("cart", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="bookings.customercart")),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cart_items", to="catalog.service")),
                ("variant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cart_items", to="catalog.servicevariant")),
            ],
            options={"ordering": ["created_at"]},
        ),
    ]
