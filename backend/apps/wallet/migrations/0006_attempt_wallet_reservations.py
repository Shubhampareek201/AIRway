import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("wallet", "0005_merge_wallet_migration_branches"),
        ("payments", "0008_installment_attempt_tender_allocations"),
    ]

    operations = [
        migrations.AlterField(
            model_name="walletreservation",
            name="payment",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="wallet_reservations", to="payments.payment",
            ),
        ),
        migrations.AddField(
            model_name="walletreservation",
            name="payment_attempt",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="wallet_reservations", to="payments.paymentattempt",
            ),
        ),
        migrations.AddConstraint(
            model_name="walletreservation",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "reserved")),
                fields=("payment_attempt",),
                name="one_active_wallet_reservation_per_attempt",
            ),
        ),
        migrations.AddConstraint(
            model_name="walletreservation",
            constraint=models.CheckConstraint(
                condition=(
                    (models.Q(("payment__isnull", False)) & models.Q(("payment_attempt__isnull", True)))
                    | (models.Q(("payment__isnull", True)) & models.Q(("payment_attempt__isnull", False)))
                ),
                name="wallet_reservation_exactly_one_source",
            ),
        ),
    ]
