import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0022_bookingextrawork_payment_status"),
        ("payments", "0010_admin_partial_refund_reasons"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentrefund",
            name="extra_work",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payment_refunds",
                to="bookings.bookingextrawork",
            ),
        ),
    ]
