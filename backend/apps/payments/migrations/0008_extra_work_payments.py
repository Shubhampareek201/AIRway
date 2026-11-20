import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0022_bookingextrawork_payment_status"),
        ("payments", "0007_appointment_group_payments"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="extra_work",
            field=models.OneToOneField(
                blank=True,
                help_text="Set only for a separately paid approved extra-work proposal.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payment",
                to="bookings.bookingextrawork",
            ),
        ),
        migrations.AddField(
            model_name="historicalpayment",
            name="extra_work",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="bookings.bookingextrawork",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="payment",
            name="unique_order_payment_stage",
        ),
        migrations.RemoveConstraint(
            model_name="payment",
            name="unique_appointment_group_payment_stage",
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=(
                    models.Q(("order__isnull", False))
                    & models.Q(("appointment_group__isnull", True))
                    & ~models.Q(("stage", "extra_work"))
                ),
                fields=("order", "stage"),
                name="unique_order_payment_stage",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("appointment_group__isnull", False), ("stage", "balance")),
                fields=("appointment_group", "stage"),
                name="unique_appointment_group_payment_stage",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("extra_work__isnull", False)),
                fields=("extra_work",),
                name="unique_extra_work_payment",
            ),
        ),
    ]
