from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0006_payment_allocation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="refundrecord",
            name="payment_attempt",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="refunds",
                to="payments.paymentattempt",
            ),
        ),
        migrations.AddField(
            model_name="refundrecord",
            name="payment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="refund_records",
                to="payments.payment",
            ),
        ),
        migrations.AddField(
            model_name="refundrecord",
            name="payment_allocation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="refund_records",
                to="payments.paymentallocation",
            ),
        ),
    ]
