from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0009_partial_refund_ledger"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paymentrefund",
            name="reason",
            field=models.CharField(
                choices=[
                    ("customer_cancellation", "Customer cancellation"),
                    ("platform_unfulfilled", "AIRway unable to fulfil"),
                    ("recurring_plan_cancellation", "Unused recurring plan visits"),
                    ("admin_adjustment", "Admin partial refund"),
                    ("dispute_resolution", "Dispute resolution"),
                ],
                max_length=32,
            ),
        ),
    ]
