from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workers", "0016_workerearning_available_at"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="workerpayoutsettlement",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "pending")),
                fields=("worker", "period_start"),
                name="one_pending_worker_settlement_per_week",
            ),
        ),
    ]
