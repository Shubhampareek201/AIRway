# Additive aggregate-tender allocation ledger.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0005_split_payment_ledger"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("gateway_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("wallet_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("installment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payment_allocations", to="payments.paymentinstallment")),
                ("payment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="installment_allocations", to="payments.payment")),
            ],
            options={
                "ordering": ["created_at", "pk"],
                "constraints": [
                    models.UniqueConstraint(fields=("payment", "installment"), name="pay_alloc_payment_inst_uniq"),
                    models.CheckConstraint(condition=models.Q(("amount__gte", 0)), name="pay_alloc_amount_nonneg"),
                    models.CheckConstraint(condition=models.Q(("gateway_amount__gte", 0)), name="pay_alloc_gateway_nonneg"),
                    models.CheckConstraint(condition=models.Q(("wallet_amount__gte", 0)), name="pay_alloc_wallet_nonneg"),
                    models.CheckConstraint(condition=models.Q(("amount", models.F("gateway_amount") + models.F("wallet_amount"))), name="pay_alloc_sources_sum"),
                ],
            },
        ),
    ]
