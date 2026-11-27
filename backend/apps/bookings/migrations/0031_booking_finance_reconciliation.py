from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0030_quote_repair_start"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingVariableCost",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.CharField(choices=[("travel", "Travel"), ("materials", "Materials"), ("payment", "Payment processing"), ("support", "Customer support"), ("rework", "Rework / service recovery"), ("other", "Other")], max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("description", models.CharField(max_length=500)),
                ("reference", models.CharField(blank=True, max_length=120)),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="variable_costs", to="bookings.booking")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recorded_booking_variable_costs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["created_at", "pk"]},
        ),
        migrations.AddConstraint(
            model_name="bookingvariablecost",
            constraint=models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="booking_variable_cost_positive"),
        ),
        migrations.CreateModel(
            name="BookingFinanceReconciliation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("other_costs_reviewed", models.BooleanField(default=False)),
                ("review_note", models.TextField(blank=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("booking", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="finance_reconciliation", to="bookings.booking")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="booking_finance_reviews", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
    ]
