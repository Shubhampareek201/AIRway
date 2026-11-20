from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0022_bookingextrawork_payment_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingDispute",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("raised_by_role", models.CharField(choices=[("customer", "Customer"), ("worker", "Worker")], max_length=12)),
                ("category", models.CharField(choices=[("service_quality", "Service quality"), ("damage", "Property or item damage"), ("payment", "Payment or refund"), ("worker_conduct", "Professional conduct"), ("customer_conduct", "Customer conduct"), ("safety", "Safety concern"), ("other", "Other")], max_length=24)),
                ("description", models.TextField(max_length=5000)),
                ("requested_outcome", models.CharField(choices=[("refund_review", "Refund review"), ("rework", "Rework or service recovery"), ("investigation", "Investigation"), ("other", "Other")], max_length=24)),
                ("evidence_items", models.JSONField(blank=True, default=list)),
                ("status", models.CharField(choices=[("open", "Open"), ("in_review", "In review"), ("resolved", "Resolved"), ("rejected", "Rejected"), ("closed", "Closed")], db_index=True, default="open", max_length=16)),
                ("resolution_note", models.TextField(blank=True, max_length=5000)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="disputes", to="bookings.booking")),
                ("raised_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="raised_booking_disputes", to=settings.AUTH_USER_MODEL)),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resolved_booking_disputes", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["status", "created_at"], name="booking_dispute_status_idx")],
                "constraints": [models.UniqueConstraint(condition=models.Q(("status__in", ["open", "in_review"])), fields=("booking",), name="one_active_dispute_per_booking")],
            },
        ),
    ]
