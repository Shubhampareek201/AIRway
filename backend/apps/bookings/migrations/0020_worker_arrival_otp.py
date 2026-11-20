from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0019_worker_location_sharing_consent"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookingassignment",
            name="arrival_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="arrival_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="arrival_otp_hash",
            field=models.CharField(blank=True, max_length=256),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="arrival_otp_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="arrival_otp_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="arrival_otp_last_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
