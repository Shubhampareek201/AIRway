import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0001_initial"),
        ("bookings", "0012_bookingworkevidence"),
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RecurringWashPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("frequency", models.CharField(choices=[("daily", "Daily"), ("alternate_day", "Alternate day"), ("twice_weekly", "Twice a week"), ("weekly", "Weekly"), ("fortnightly", "Fortnightly")], max_length=20)),
                ("duration_days", models.PositiveSmallIntegerField()),
                ("starts_on", models.DateField()),
                ("ends_on", models.DateField()),
                ("preferred_time_window", models.CharField(blank=True, choices=[("Morning", "Morning"), ("Afternoon", "Afternoon"), ("Evening", "Evening")], max_length=12)),
                ("vehicle_type", models.CharField(max_length=40)),
                ("vehicle_quantity", models.PositiveSmallIntegerField(default=1)),
                ("quoted_total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("status", models.CharField(choices=[("awaiting_quote", "Awaiting quote"), ("awaiting_payment", "Awaiting payment"), ("paid_pending_setup", "Paid - schedule setup pending"), ("active", "Active"), ("paused", "Paused"), ("cancelled", "Cancelled"), ("completed", "Completed")], db_index=True, default="awaiting_quote", max_length=20)),
                ("plan_snapshot", models.JSONField(blank=True, default=dict)),
                ("quote_accepted_at", models.DateTimeField(blank=True, null=True)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("paused_at", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("admin_notes", models.TextField(blank=True)),
                ("address", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recurring_wash_plans", to="accounts.address")),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recurring_wash_plans", to=settings.AUTH_USER_MODEL)),
                ("order", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="recurring_wash_plan", to="bookings.order")),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recurring_wash_plans", to="catalog.service")),
                ("source_booking", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="recurring_wash_plan", to="bookings.booking")),
                ("variant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="recurring_wash_plans", to="catalog.servicevariant")),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["status", "starts_on"], name="wash_plan_status_start_idx"),
                    models.Index(fields=["customer", "status"], name="wash_plan_customer_status_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("vehicle_quantity__gte", 1)), name="wash_plan_vehicle_qty_gte_1"),
                    models.CheckConstraint(condition=models.Q(("ends_on__gte", models.F("starts_on"))), name="wash_plan_end_after_start"),
                ],
            },
        ),
    ]
