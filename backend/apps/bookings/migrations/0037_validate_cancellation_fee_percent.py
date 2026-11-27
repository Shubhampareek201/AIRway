import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0036_late_cancellation_policy"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dispatchconfiguration",
            name="late_cancellation_fee_percent",
            field=models.PositiveSmallIntegerField(
                default=30,
                help_text="Percentage retained from the captured advance payment for late customer cancellations.",
                validators=[django.core.validators.MaxValueValidator(99)],
            ),
        ),
    ]
