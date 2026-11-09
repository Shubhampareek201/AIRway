from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0008_installment_attempt_tender_allocations"),
    ]

    operations = [
        migrations.AddField(
            model_name="refundrecord",
            name="gateway_refund_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="refundrecord",
            name="wallet_refund_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="refundrecord",
            name="wallet_refunded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="refundrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(("gateway_refund_amount__gte", 0)),
                name="refund_gateway_nonneg",
            ),
        ),
        migrations.AddConstraint(
            model_name="refundrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(("wallet_refund_amount__gte", 0)),
                name="refund_wallet_nonneg",
            ),
        ),
        migrations.AddConstraint(
            model_name="refundrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(("refund_amount", models.F("gateway_refund_amount") + models.F("wallet_refund_amount"))),
                name="refund_sources_sum",
            ),
        ),
    ]
