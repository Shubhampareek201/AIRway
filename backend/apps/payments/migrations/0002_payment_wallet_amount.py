from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0003_order_payment"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="wallet_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Amount reserved from the customer wallet for this order payment.",
                max_digits=10,
            ),
        ),
        migrations.AddField(
            model_name="historicalpayment",
            name="wallet_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Amount reserved from the customer wallet for this order payment.",
                max_digits=10,
            ),
        ),
    ]
