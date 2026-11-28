import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0039_arrival_and_start_otp"),
        ("workers", "0020_worker_zone_change_requests"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingStartOTPException",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reason", models.TextField()),
                ("status", models.CharField(choices=[("pending", "Pending review"), ("approved", "Approved"), ("rejected", "Rejected")], default="pending", max_length=12)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("review_note", models.TextField(blank=True)),
                ("assignment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="start_otp_exceptions", to="bookings.bookingassignment")),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="start_otp_exceptions", to="bookings.booking")),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="start_otp_exceptions", to="workers.workerprofile")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_start_otp_exceptions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="bookingstartotpexception",
            constraint=models.UniqueConstraint(condition=models.Q(("status", "pending")), fields=("assignment",), name="unique_pending_start_otp_exception"),
        ),
    ]
