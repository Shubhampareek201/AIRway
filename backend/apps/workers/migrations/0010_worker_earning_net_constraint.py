from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workers", "0009_worker_earning_adjustments"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="workerearning",
            constraint=models.CheckConstraint(
                condition=models.Q(("net_amount__isnull", True))
                | models.Q(("net_amount__gte", 0)),
                name="worker_earning_net_nonnegative",
            ),
        ),
    ]
