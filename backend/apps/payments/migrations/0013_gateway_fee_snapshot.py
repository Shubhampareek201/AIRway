from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payments", "0012_paymentrefund_dispute")]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="gateway_fee_amount",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True,
                help_text="Actual Razorpay processing fee, excluding GST; null until confirmed by Razorpay.",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="gateway_fee_tax_amount",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True,
                help_text="GST charged by Razorpay on its processing fee; null until confirmed by Razorpay.",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="gateway_fee_recorded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
