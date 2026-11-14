from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallet", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="wallettransaction",
            name="razorpay_payment_id",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
