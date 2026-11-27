from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0031_booking_finance_reconciliation"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookingextrawork",
            name="worker_payout_amount",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="Worker's immutable payout snapshot for this customer-approved extra-work scope.", max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="bookingextrawork",
            name="worker_payout_snapshot",
            field=models.JSONField(blank=True, default=dict, help_text="Calculation inputs captured when the extra-work proposal was created."),
        ),
    ]
