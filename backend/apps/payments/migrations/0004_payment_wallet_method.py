from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0002_payment_wallet_amount"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="method",
            field=models.CharField(
                choices=[("cod", "Cash on Delivery"), ("razorpay", "Razorpay"), ("wallet", "AIRway Wallet")],
                default="cod",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="historicalpayment",
            name="method",
            field=models.CharField(
                choices=[("cod", "Cash on Delivery"), ("razorpay", "Razorpay"), ("wallet", "AIRway Wallet")],
                default="cod",
                max_length=20,
            ),
        ),
    ]
