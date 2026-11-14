from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0010_booking_completion_otp"),
        ("payments", "0005_staged_order_payments"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentRefund",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("wallet_amount", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("gateway_amount", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("reason", models.CharField(choices=[("customer_cancellation", "Customer cancellation"), ("platform_unfulfilled", "AIRway unable to fulfil")], max_length=32)),
                ("status", models.CharField(choices=[("processing", "Processing"), ("pending", "Pending"), ("processed", "Processed"), ("failed", "Failed")], db_index=True, default="processing", max_length=12)),
                ("gateway_refund_id", models.CharField(blank=True, db_index=True, max_length=100)),
                ("failure_reason", models.CharField(blank=True, max_length=500)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payment_refunds", to="bookings.booking")),
                ("order_item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payment_refunds", to="bookings.orderitem")),
                ("payment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="refunds", to="payments.payment")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="paymentrefund",
            constraint=models.UniqueConstraint(fields=("payment", "booking"), name="unique_payment_refund_booking"),
        ),
        migrations.AddConstraint(
            model_name="paymentrefund",
            constraint=models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="payment_refund_amount_positive"),
        ),
        migrations.AddConstraint(
            model_name="paymentrefund",
            constraint=models.CheckConstraint(condition=models.Q(("wallet_amount__gte", 0), ("gateway_amount__gte", 0)), name="payment_refund_components_nonnegative"),
        ),
    ]
