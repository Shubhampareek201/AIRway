import django.db.models.deletion
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0009_alter_workeroffer_booking"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceOTP",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("purpose", models.CharField(choices=[("start", "Service Start"), ("complete", "Service Completion")], max_length=12)),
                ("code_hash", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_sent_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="service_otps", to="bookings.booking")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="serviceotp",
            index=models.Index(fields=["booking", "purpose", "verified_at"], name="svc_otp_booking_idx"),
        ),
        migrations.AddIndex(
            model_name="serviceotp",
            index=models.Index(fields=["expires_at"], name="svc_otp_expiry_idx"),
        ),
    ]
