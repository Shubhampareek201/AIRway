from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0018_workeroffer_appointment_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="customercart",
            name="group_messages",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
