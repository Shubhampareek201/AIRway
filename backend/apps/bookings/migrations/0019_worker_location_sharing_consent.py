from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0018_workeroffer_appointment_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookingassignment",
            name="location_sharing_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Worker-controlled permission to share foreground GPS with the customer during the 30-minute pre-appointment window and active job.",
            ),
        ),
    ]
