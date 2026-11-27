from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("workers", "0014_worker_referral_rewards_and_withdrawal_idempotency"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkerPayoutSettlement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                ("total_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("status", models.CharField(choices=[("pending", "Awaiting payout"), ("paid", "Paid")], db_index=True, default="pending", max_length=12)),
                ("payout_reference", models.CharField(blank=True, max_length=120)),
                ("admin_note", models.TextField(blank=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_worker_payout_settlements", to=settings.AUTH_USER_MODEL)),
                ("paid_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="worker_payout_settlements", to=settings.AUTH_USER_MODEL)),
                ("worker", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payout_settlements", to="workers.workerprofile")),
            ],
            options={
                "ordering": ["-period_start", "-created_at"],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("period_end__gte", models.F("period_start"))), name="worker_payout_period_valid"),
                    models.CheckConstraint(condition=models.Q(("total_amount__gt", 0)), name="worker_payout_settlement_positive"),
                ],
            },
        ),
        migrations.AddField(
            model_name="workerearning",
            name="settlement_batch",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="earnings", to="workers.workerpayoutsettlement"),
        ),
    ]
