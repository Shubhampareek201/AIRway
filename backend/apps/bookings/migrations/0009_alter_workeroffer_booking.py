from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0008_dispatch_priority_strategies"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workeroffer",
            name="booking",
            field=models.ForeignKey(
                help_text="For an order offer, this is the first booking line used as the offer's display anchor.",
                on_delete=models.deletion.CASCADE,
                related_name="worker_offers",
                to="bookings.booking",
            ),
        ),
    ]
