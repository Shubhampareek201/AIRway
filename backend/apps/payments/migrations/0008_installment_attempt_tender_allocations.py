from django.db import migrations, models
import django.db.models.deletion


def backfill_attempt_tender_sources(apps, schema_editor):
    PaymentAttempt = apps.get_model("payments", "PaymentAttempt")
    PaymentAttempt.objects.filter(provider="wallet").update(wallet_amount=models.F("amount"))
    PaymentAttempt.objects.exclude(provider="wallet").update(gateway_amount=models.F("amount"))


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0007_refund_payment_links"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentattempt",
            name="gateway_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="paymentattempt",
            name="wallet_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.RunPython(backfill_attempt_tender_sources, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="paymentattempt",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount", models.F("gateway_amount") + models.F("wallet_amount"))),
                name="attempt_sources_sum",
            ),
        ),
        migrations.AddConstraint(
            model_name="paymentattempt",
            constraint=models.CheckConstraint(condition=models.Q(("gateway_amount__gte", 0)), name="attempt_gateway_nonneg"),
        ),
        migrations.AddConstraint(
            model_name="paymentattempt",
            constraint=models.CheckConstraint(condition=models.Q(("wallet_amount__gte", 0)), name="attempt_wallet_nonneg"),
        ),
        migrations.AlterField(
            model_name="paymentallocation",
            name="payment",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="installment_allocations", to="payments.payment"),
        ),
        migrations.AddField(
            model_name="paymentallocation",
            name="payment_attempt",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="allocations", to="payments.paymentattempt"),
        ),
        migrations.AddConstraint(
            model_name="paymentallocation",
            constraint=models.UniqueConstraint(fields=("payment_attempt", "installment"), name="pay_alloc_attempt_inst_uniq"),
        ),
        migrations.AddConstraint(
            model_name="paymentallocation",
            constraint=models.CheckConstraint(
                condition=(
                    (models.Q(("payment__isnull", False)) & models.Q(("payment_attempt__isnull", True)))
                    | (models.Q(("payment__isnull", True)) & models.Q(("payment_attempt__isnull", False)))
                ),
                name="pay_alloc_exactly_one_source",
            ),
        ),
    ]
