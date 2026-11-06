from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wallet", "0003_reservation_payment_fk"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="walletreservation",
            constraint=models.UniqueConstraint(
                fields=("payment",),
                condition=models.Q(("status", "reserved")),
                name="one_active_wallet_reservation_per_payment",
            ),
        ),
    ]
