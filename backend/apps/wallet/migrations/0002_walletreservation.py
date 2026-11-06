import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0002_payment_wallet_amount"),
        ("wallet", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="WalletReservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("status", models.CharField(choices=[("reserved", "Reserved"), ("captured", "Captured"), ("released", "Released")], db_index=True, default="reserved", max_length=12)),
                ("captured_at", models.DateTimeField(blank=True, null=True)),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                ("payment", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="wallet_reservation", to="payments.payment")),
                ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reservations", to="wallet.wallet")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="walletreservation",
            constraint=models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="wallet_reservation_amount_positive"),
        ),
    ]
