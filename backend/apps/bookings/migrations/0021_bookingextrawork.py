import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0020_worker_arrival_otp"),
        ("workers", "0006_workerprofile_gps_coordinates"),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingExtraWork",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("request_key", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("reason", models.CharField(max_length=500)),
                ("line_items", models.JSONField(default=list, help_text="Immutable item snapshot: description, quantity, unit price and line total.")),
                ("subtotal", models.DecimalField(decimal_places=2, max_digits=12)),
                ("tax_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("total_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("additional_duration_minutes", models.PositiveSmallIntegerField(default=0)),
                ("status", models.CharField(choices=[("pending_customer", "Awaiting customer decision"), ("approved", "Approved"), ("rejected", "Rejected"), ("expired", "Expired"), ("cancelled", "Cancelled")], db_index=True, default="pending_customer", max_length=24)),
                ("payment_choice", models.CharField(blank=True, choices=[("separate", "Separate payment"), ("add_to_balance", "Add to appointment balance")], max_length=24)),
                ("customer_response_note", models.CharField(blank=True, max_length=1000)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("responded_at", models.DateTimeField(blank=True, null=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("appointment_group", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="extra_work_requests", to="bookings.appointmentgroup")),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="extra_work_requests", to="bookings.booking")),
                ("worker", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="extra_work_requests", to="workers.workerprofile")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="bookingextrawork",
            index=models.Index(fields=["booking", "status"], name="booking_extra_work_status_idx"),
        ),
        migrations.AddIndex(
            model_name="bookingextrawork",
            index=models.Index(fields=["appointment_group", "status"], name="group_extra_work_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="bookingextrawork",
            constraint=models.CheckConstraint(condition=models.Q(("subtotal__gt", 0)), name="extra_work_subtotal_positive"),
        ),
        migrations.AddConstraint(
            model_name="bookingextrawork",
            constraint=models.CheckConstraint(condition=models.Q(("total_amount__gt", 0)), name="extra_work_total_positive"),
        ),
    ]
