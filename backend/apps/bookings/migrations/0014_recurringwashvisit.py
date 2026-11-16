import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0013_recurringwashplan"),
    ]

    operations = [
        migrations.CreateModel(
            name="RecurringWashVisit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("visit_number", models.PositiveSmallIntegerField()),
                ("scheduled_at", models.DateTimeField(db_index=True)),
                ("prepaid_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("status", models.CharField(choices=[("pending_setup", "Pending booking setup"), ("booked", "Booking created"), ("in_progress", "In progress"), ("completed", "Completed"), ("cancelled", "Cancelled"), ("skipped", "Skipped")], db_index=True, default="pending_setup", max_length=20)),
                ("admin_notes", models.TextField(blank=True)),
                ("booking", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="recurring_wash_visit", to="bookings.booking")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="visits", to="bookings.recurringwashplan")),
            ],
            options={
                "ordering": ["scheduled_at", "visit_number"],
                "indexes": [models.Index(fields=["status", "scheduled_at"], name="wash_visit_status_time_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("plan", "visit_number"), name="unique_wash_plan_visit_number"),
                    models.UniqueConstraint(fields=("plan", "scheduled_at"), name="unique_wash_plan_visit_time"),
                    models.CheckConstraint(condition=models.Q(("visit_number__gte", 1)), name="wash_visit_number_gte_1"),
                ],
            },
        ),
    ]
