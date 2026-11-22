from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0027_initial_launch_offer_window"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="worker_payout_snapshot",
            field=models.JSONField(blank=True, default=dict, help_text="Private immutable worker payout and required-material snapshot; never expose through customer serializers."),
        ),
        migrations.AddField(
            model_name="historicalbooking",
            name="worker_payout_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
