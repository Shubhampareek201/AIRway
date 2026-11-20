import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0017_appointment_group_foundation"),
        ("payments", "0006_paymentrefund"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="appointment_group",
            field=models.ForeignKey(
                blank=True,
                help_text="Set for a balance payment belonging to one completed appointment group.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payments",
                to="bookings.appointmentgroup",
            ),
        ),
        migrations.AddField(
            model_name="historicalpayment",
            name="appointment_group",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="bookings.appointmentgroup",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="payment",
            name="unique_order_payment_stage",
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=(
                    models.Q(("order__isnull", False))
                    & models.Q(("appointment_group__isnull", True))
                ),
                fields=("order", "stage"),
                name="unique_order_payment_stage",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("appointment_group__isnull", False)),
                fields=("appointment_group", "stage"),
                name="unique_appointment_group_payment_stage",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("appointment_group__isnull", True))
                    | models.Q(("order__isnull", False))
                ),
                name="group_payment_requires_parent_order",
            ),
        ),
    ]
