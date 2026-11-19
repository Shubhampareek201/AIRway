from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0017_appointment_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="workeroffer",
            name="appointment_group",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="worker_offers",
                to="bookings.appointmentgroup",
            ),
        ),
    ]
