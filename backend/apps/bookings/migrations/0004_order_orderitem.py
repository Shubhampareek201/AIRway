# Generated for grouped multi-service checkout.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0003_customercart_cartitem"),
        ("accounts", "0003_alter_user_phone"),
    ]

    operations = [
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("awaiting_assignment", "Awaiting Assignment"), ("awaiting_payment", "Awaiting Payment"), ("paid", "Paid"), ("partially_cancelled", "Partially Cancelled"), ("cancelled", "Cancelled")], db_index=True, default="awaiting_assignment", max_length=24)),
                ("currency", models.CharField(default="INR", max_length=3)),
                ("subtotal", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("tax_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("discount_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("total_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("address", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="service_orders", to="accounts.address")),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="service_orders", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"], "indexes": [models.Index(fields=["customer", "status"], name="book_ord_cust_stat_idx"), models.Index(fields=["created_at", "status"], name="book_ord_created_stat_idx")]},
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("service_snapshot", models.JSONField(blank=True, default=dict)),
                ("pricing_snapshot", models.JSONField(blank=True, default=dict)),
                ("line_subtotal", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("tax_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("line_total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("booking", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="order_item", to="bookings.booking")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="items", to="bookings.order")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddConstraint(
            model_name="orderitem",
            constraint=models.CheckConstraint(condition=models.Q(("quantity__gte", 1)), name="order_item_quantity_gte_1"),
        ),
    ]
