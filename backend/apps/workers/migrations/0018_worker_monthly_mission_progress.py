from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("workers", "0017_one_pending_worker_settlement_per_week")]

    operations = [
        migrations.CreateModel(
            name="WorkerMonthlyMissionProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("month_start", models.DateField(db_index=True, help_text="First calendar day of the mission month.")),
                ("eligible_jobs_count", models.PositiveIntegerField(default=0)),
                ("worker", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="monthly_mission_progress", to="workers.workerprofile")),
            ],
            options={
                "ordering": ["-month_start", "worker_id"],
                "indexes": [models.Index(fields=["month_start", "eligible_jobs_count"], name="worker_month_mission_idx")],
                "constraints": [models.UniqueConstraint(fields=("worker", "month_start"), name="unique_worker_monthly_mission")],
            },
        ),
    ]
