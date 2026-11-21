import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workers", "0010_worker_earning_net_constraint"),
        ("bookings", "0022_bookingextrawork_payment_status"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="workerearning",
            name="unique_worker_earning_per_booking",
        ),
        migrations.AddField(
            model_name="workerearning",
            name="extra_work",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="worker_earnings",
                to="bookings.bookingextrawork",
            ),
        ),
        migrations.AddConstraint(
            model_name="workerearning",
            constraint=models.UniqueConstraint(
                condition=models.Q(("extra_work__isnull", True)),
                fields=("booking",),
                name="unique_worker_service_earning_per_booking",
            ),
        ),
        migrations.AddConstraint(
            model_name="workerearning",
            constraint=models.UniqueConstraint(
                condition=models.Q(("extra_work__isnull", False)),
                fields=("extra_work",),
                name="unique_worker_earning_per_extra_work",
            ),
        ),
    ]
