# Generated for parent-level order payments; existing booking payments remain supported.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0002_payment_failed_at"),
        ("bookings", "0004_order_orderitem"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="booking",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payment", to="bookings.booking"),
        ),
        migrations.AddField(
            model_name="payment",
            name="order",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payment", to="bookings.order"),
        ),
        migrations.AddField(
            model_name="historicalpayment",
            name="order",
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name="+", to="bookings.order"),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.CheckConstraint(
                condition=(
                    (models.Q(("booking__isnull", False), ("order__isnull", True)))
                    | (models.Q(("booking__isnull", True), ("order__isnull", False)))
                ),
                name="payment_exactly_one_booking_or_order",
            ),
        ),
    ]
