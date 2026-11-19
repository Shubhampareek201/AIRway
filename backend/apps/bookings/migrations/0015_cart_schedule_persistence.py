from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0014_recurringwashvisit"),
    ]

    operations = [
        migrations.AddField(
            model_name="customercart",
            name="schedule_mode",
            field=models.CharField(default="separate", max_length=24),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="schedule_data",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
