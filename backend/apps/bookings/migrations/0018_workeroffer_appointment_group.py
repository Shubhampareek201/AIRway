from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0017_appointment_group_foundation"),
    ]

    operations = [
        migrations.AddField(
            model_name="workeroffer",
            name="appointment_group",
            field=models.ForeignKey(
                blank=True,
                help_text="Set for a single-worker offer covering every service in one appointment group.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="worker_offers",
                to="bookings.appointmentgroup",
            ),
        ),
        migrations.AddConstraint(
            model_name="workeroffer",
            constraint=models.UniqueConstraint(
                condition=models.Q(("appointment_group__isnull", False)),
                fields=("appointment_group", "worker"),
                name="unique_group_offer_worker",
            ),
        ),
    ]
