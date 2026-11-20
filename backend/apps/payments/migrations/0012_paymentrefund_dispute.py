from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0024_bookingdisputeevidence"),
        ("payments", "0011_refund_extra_work_target"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentrefund",
            name="dispute",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payment_refunds",
                to="bookings.bookingdispute",
            ),
        ),
    ]
