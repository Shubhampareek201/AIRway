# Additive ledger tables. Legacy Payment rows are intentionally untouched.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0003_order_payment"),
        ("payments", "0004_payment_wallet_method"),
        ("bookings", "0009_alter_workeroffer_booking"),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingFinancialPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("currency", models.CharField(default="INR", max_length=3)),
                ("gross_total", models.DecimalField(decimal_places=2, max_digits=12)),
                ("advance_due", models.DecimalField(decimal_places=2, max_digits=12)),
                ("balance_due", models.DecimalField(decimal_places=2, max_digits=12)),
                ("advance_captured", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("balance_captured", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("refunded_total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("platform_fee_deducted", models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ("calculation_version", models.CharField(default="split-50-50-v1", max_length=24)),
                ("pricing_snapshot", models.JSONField(default=dict)),
                ("state", models.CharField(choices=[("active", "Active"), ("cancelled", "Cancelled"), ("closed", "Closed")], default="active", max_length=16)),
                ("booking", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="financial_plan", to="bookings.booking")),
            ],
            options={"constraints": [
                models.CheckConstraint(condition=models.Q(("gross_total__gte", 0)), name="finplan_total_nonnegative"),
                models.CheckConstraint(condition=models.Q(("advance_due__gte", 0)), name="finplan_advance_nonnegative"),
                models.CheckConstraint(condition=models.Q(("balance_due__gte", 0)), name="finplan_balance_nonnegative"),
                models.CheckConstraint(condition=models.Q(("advance_captured__gte", 0)), name="finplan_advance_captured_nonnegative"),
                models.CheckConstraint(condition=models.Q(("balance_captured__gte", 0)), name="finplan_balance_captured_nonnegative"),
                models.CheckConstraint(condition=models.Q(("refunded_total__gte", 0)), name="finplan_refund_nonnegative"),
                models.CheckConstraint(condition=models.Q(("advance_due__lte", models.F("gross_total"))), name="finplan_advance_lte_total"),
                models.CheckConstraint(condition=models.Q(("balance_due__lte", models.F("gross_total"))), name="finplan_balance_lte_total"),
            ]},
        ),
        migrations.CreateModel(
            name="PaymentInstallment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("kind", models.CharField(choices=[("advance", "50% Booking Advance"), ("final_balance", "50% Completion Balance")], max_length=20)),
                ("amount_due", models.DecimalField(decimal_places=2, max_digits=12)),
                ("amount_captured", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("status", models.CharField(choices=[("not_due", "Not Due"), ("due", "Due"), ("processing", "Processing"), ("partially_paid", "Partially Paid"), ("paid", "Paid"), ("failed", "Failed"), ("cancelled", "Cancelled")], db_index=True, default="not_due", max_length=20)),
                ("due_at", models.DateTimeField(blank=True, null=True)),
                ("settled_at", models.DateTimeField(blank=True, null=True)),
                ("financial_plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="installments", to="payments.bookingfinancialplan")),
            ],
            options={"ordering": ["created_at"], "constraints": [
                models.UniqueConstraint(fields=("financial_plan", "kind"), name="uniq_finplan_installment_kind"),
                models.CheckConstraint(condition=models.Q(("amount_due__gte", 0)), name="installment_due_nonnegative"),
                models.CheckConstraint(condition=models.Q(("amount_captured__gte", 0)), name="installment_captured_nonnegative"),
                models.CheckConstraint(condition=models.Q(("amount_captured__lte", models.F("amount_due"))), name="installment_captured_lte_due"),
            ]},
        ),
        migrations.CreateModel(
            name="PaymentAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("provider", models.CharField(choices=[("razorpay", "Razorpay"), ("wallet", "AIRway Wallet")], default="razorpay", max_length=16)),
                ("idempotency_key", models.CharField(max_length=100, unique=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="INR", max_length=3)),
                ("provider_order_id", models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ("provider_payment_id", models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ("status", models.CharField(choices=[("created", "Created"), ("authorized", "Authorized"), ("captured", "Captured"), ("failed", "Failed"), ("refund_pending", "Refund Pending"), ("refunded", "Refunded")], db_index=True, default="created", max_length=20)),
                ("captured_at", models.DateTimeField(blank=True, null=True)),
                ("failed_at", models.DateTimeField(blank=True, null=True)),
                ("provider_payload", models.JSONField(blank=True, default=dict)),
                ("installment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attempts", to="payments.paymentinstallment")),
            ],
            options={"ordering": ["-created_at"], "constraints": [
                models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="payment_attempt_amount_positive"),
            ]},
        ),
        migrations.CreateModel(
            name="RefundRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("idempotency_key", models.CharField(max_length=120, unique=True)),
                ("reason", models.CharField(choices=[("customer_cancellation", "Customer Cancellation"), ("provider_unavailable", "Provider Unavailable"), ("platform_cancellation", "Platform Cancellation"), ("payment_reconciliation", "Payment Reconciliation"), ("support_resolution", "Support Resolution")], max_length=32)),
                ("gross_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("platform_fee", models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ("refund_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("provider_refund_id", models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ("status", models.CharField(choices=[("requested", "Requested"), ("pending", "Pending with Provider"), ("processed", "Processed"), ("failed", "Failed")], db_index=True, default="requested", max_length=16)),
                ("requested_at", models.DateTimeField(blank=True, null=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("provider_payload", models.JSONField(blank=True, default=dict)),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="refund_records", to="bookings.booking")),
                ("payment_attempt", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="refunds", to="payments.paymentattempt")),
            ],
            options={"ordering": ["-created_at"], "constraints": [
                models.CheckConstraint(condition=models.Q(("gross_amount__gte", 0)), name="refund_gross_nonnegative"),
                models.CheckConstraint(condition=models.Q(("platform_fee__gte", 0)), name="refund_fee_nonnegative"),
                models.CheckConstraint(condition=models.Q(("refund_amount__gte", 0)), name="refund_amount_nonnegative"),
                models.CheckConstraint(condition=models.Q(("refund_amount__lte", models.F("gross_amount"))), name="refund_lte_gross"),
            ]},
        ),
        migrations.CreateModel(
            name="ServiceOTPChallenge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("purpose", models.CharField(choices=[("start", "Service Start"), ("completion", "Service Completion")], max_length=12)),
                ("code_hash", models.CharField(max_length=128)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("max_attempts", models.PositiveSmallIntegerField(default=5)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("invalidated_at", models.DateTimeField(blank=True, null=True)),
                ("delivery_reference", models.CharField(blank=True, max_length=100)),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="service_otp_challenges", to="bookings.booking")),
            ],
            options={"ordering": ["-created_at"], "indexes": [
                models.Index(fields=["booking", "purpose", "consumed_at"], name="payments_ser_booking_5e94a2_idx"),
            ]},
        ),
    ]
