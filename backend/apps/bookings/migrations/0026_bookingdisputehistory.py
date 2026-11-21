from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion



def backfill_existing_dispute_history(apps, schema_editor):
    Dispute = apps.get_model("bookings", "BookingDispute")
    History = apps.get_model("bookings", "BookingDisputeHistory")
    rows = [
        History(
            dispute_id=dispute.pk,
            from_status="",
            to_status=dispute.status,
            changed_by_id=dispute.raised_by_id,
            note="Initial status recorded during dispute audit-history rollout.",
        )
        for dispute in Dispute.objects.all().iterator()
    ]
    History.objects.bulk_create(rows, batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0025_bookingreworkproposal"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingDisputeHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("from_status", models.CharField(blank=True, max_length=16)),
                ("to_status", models.CharField(choices=[("open", "Open"), ("in_review", "In review"), ("resolved", "Resolved"), ("rejected", "Rejected"), ("closed", "Closed")], max_length=16)),
                ("note", models.TextField(blank=True, max_length=5000)),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="booking_dispute_status_changes", to=settings.AUTH_USER_MODEL)),
                ("dispute", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="status_history", to="bookings.bookingdispute")),
            ],
            options={"ordering": ["created_at", "pk"]},
        ),
    ]
