from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0004_payment_wallet_method"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="order",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payments",
                to="bookings.order",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="stage",
            field=models.CharField(
                choices=[
                    ("legacy", "Legacy full payment"),
                    ("advance", "30% advance"),
                    ("balance", "70% balance"),
                ],
                db_index=True,
                default="legacy",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="historicalpayment",
            name="stage",
            field=models.CharField(
                choices=[
                    ("legacy", "Legacy full payment"),
                    ("advance", "30% advance"),
                    ("balance", "70% balance"),
                ],
                db_index=True,
                default="legacy",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("order__isnull", False)),
                fields=("order", "stage"),
                name="unique_order_payment_stage",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("razorpay_order_id", ""), _negated=True),
                fields=("razorpay_order_id",),
                name="unique_razorpay_order_id",
            ),
        ),
    ]
