from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0037_validate_cancellation_fee_percent"),
    ]

    operations = [
        migrations.AddField(
            model_name="dispatchconfiguration",
            name="no_show_grace_minutes",
            field=models.PositiveSmallIntegerField(
                default=30,
                help_text="Minutes after the scheduled start before a customer can report a worker no-show.",
            ),
        ),
    ]
