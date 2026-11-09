import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0003_order_payment"),
        ("payments", "0004_payment_wallet_method"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("paid", "Paid"),
                    ("partially_paid", "Partially Paid"),
                    ("refund_pending", "Refund Pending"),
                    ("failed", "Failed"),
                    ("refunded", "Refunded"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="historicalpayment",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("paid", "Paid"),
                    ("partially_paid", "Partially Paid"),
                    ("refund_pending", "Refund Pending"),
                    ("failed", "Failed"),
                    ("refunded", "Refunded"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="PaymentInstallment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("kind", models.CharField(choices=[("advance", "Booking Advance"), ("balance", "Completion Balance")], max_length=16)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("wallet_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("paid", "Paid")], default="pending", max_length=16)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("payment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="installments", to="payments.payment")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddConstraint(
            model_name="paymentinstallment",
            constraint=models.UniqueConstraint(fields=("payment", "kind"), name="uniq_payment_installment_kind"),
        ),
        migrations.AddConstraint(
            model_name="paymentinstallment",
            constraint=models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="payment_installment_amount_positive"),
        ),
        migrations.AddConstraint(
            model_name="paymentinstallment",
            constraint=models.CheckConstraint(condition=models.Q(("wallet_amount__gte", 0)), name="payment_installment_wallet_nonnegative"),
        ),
        migrations.CreateModel(
            name="PaymentAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("attempt_number", models.PositiveIntegerField()),
                ("amount", models.DecimalField(decimal_places=2, help_text="Gateway amount only; wallet contribution is stored separately.", max_digits=12)),
                ("wallet_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("method", models.CharField(choices=[("cod", "Cash on Delivery"), ("razorpay", "Razorpay"), ("wallet", "AIRway Wallet")], default="razorpay", max_length=20)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("paid", "Paid"), ("failed", "Failed"), ("refunded", "Refunded")], db_index=True, default="pending", max_length=16)),
                ("razorpay_order_id", models.CharField(blank=True, max_length=100, unique=True)),
                ("razorpay_payment_id", models.CharField(blank=True, max_length=100, unique=True)),
                ("razorpay_signature", models.CharField(blank=True, max_length=255)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("failed_at", models.DateTimeField(blank=True, null=True)),
                ("raw_response", models.JSONField(blank=True, default=dict)),
                ("installment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attempts", to="payments.paymentinstallment")),
            ],
            options={"ordering": ["attempt_number"]},
        ),
        migrations.AddConstraint(
            model_name="paymentattempt",
            constraint=models.UniqueConstraint(fields=("installment", "attempt_number"), name="uniq_installment_attempt_number"),
        ),
        migrations.AddConstraint(
            model_name="paymentattempt",
            constraint=models.CheckConstraint(condition=models.Q(("amount__gte", 0)), name="payment_attempt_amount_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="paymentattempt",
            constraint=models.CheckConstraint(condition=models.Q(("wallet_amount__gte", 0)), name="payment_attempt_wallet_nonnegative"),
        ),
        migrations.CreateModel(
            name="PaymentRefund",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("idempotency_key", models.CharField(max_length=120, unique=True)),
                ("gateway_refund_id", models.CharField(blank=True, db_index=True, max_length=100)),
                ("gateway_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("wallet_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("platform_fee", models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processed", "Processed"), ("failed", "Failed")], db_index=True, default="pending", max_length=16)),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("raw_response", models.JSONField(blank=True, default=dict)),
                ("attempt", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="refunds", to="payments.paymentattempt")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="paymentrefund",
            constraint=models.CheckConstraint(condition=models.Q(("gateway_amount__gte", 0)), name="payment_refund_gateway_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="paymentrefund",
            constraint=models.CheckConstraint(condition=models.Q(("wallet_amount__gte", 0)), name="payment_refund_wallet_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="paymentrefund",
            constraint=models.CheckConstraint(condition=models.Q(("platform_fee__gte", 0)), name="payment_refund_fee_nonnegative"),
        ),
    ]
