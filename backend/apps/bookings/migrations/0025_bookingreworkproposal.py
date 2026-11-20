from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0024_bookingdisputeevidence"),
        ("workers", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingReworkProposal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("scheduled_at", models.DateTimeField()),
                ("status", models.CharField(choices=[("pending_customer", "Awaiting customer decision"), ("accepted", "Accepted"), ("declined", "Declined"), ("expired", "Expired")], db_index=True, default="pending_customer", max_length=24)),
                ("responded_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_booking_rework_proposals", to=settings.AUTH_USER_MODEL)),
                ("dispute", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="rework_proposals", to="bookings.bookingdispute")),
                ("followup_booking", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="rework_source", to="bookings.booking")),
                ("worker", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="rework_proposals", to="workers.workerprofile")),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["status", "scheduled_at"], name="rework_status_slot_idx")],
                "constraints": [models.UniqueConstraint(condition=models.Q(("status", "pending_customer")), fields=("dispute",), name="one_pending_rework_proposal_per_dispute")],
            },
        ),
    ]
