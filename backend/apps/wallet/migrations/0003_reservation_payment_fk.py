import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallet", "0002_walletreservation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="walletreservation",
            name="payment",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="wallet_reservations",
                to="payments.payment",
            ),
        ),
    ]
