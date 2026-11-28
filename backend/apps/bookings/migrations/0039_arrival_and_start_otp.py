from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0038_worker_no_show_grace_period"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookingassignment",
            name="arrived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="arrival_latitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="arrival_longitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="arrival_accuracy_m",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="start_otp_hash",
            field=models.CharField(blank=True, max_length=256),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="start_otp_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="start_otp_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="start_otp_last_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="start_otp_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
