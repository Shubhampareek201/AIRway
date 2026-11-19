from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0015_cart_schedule_persistence"),
        ("workers", "0006_workerprofile_gps_coordinates"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookingassignment",
            name="live_latitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="live_longitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="live_accuracy_m",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True),
        ),
        migrations.AddField(
            model_name="bookingassignment",
            name="live_location_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
