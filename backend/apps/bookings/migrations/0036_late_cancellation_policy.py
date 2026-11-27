from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0035_customer_campaigns"),
    ]

    operations = [
        migrations.AddField(
            model_name="dispatchconfiguration",
            name="late_cancellation_window_hours",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Hours before the appointment when the late-cancellation fee applies. Zero disables the fee.",
            ),
        ),
        migrations.AddField(
            model_name="dispatchconfiguration",
            name="late_cancellation_fee_percent",
            field=models.PositiveSmallIntegerField(
                default=30,
                help_text="Percentage retained from the captured advance payment for late customer cancellations.",
            ),
        ),
    ]
