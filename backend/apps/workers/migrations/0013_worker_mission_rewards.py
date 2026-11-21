from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("workers", "0012_worker_leave_approval_workflow"),
        ("bookings", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkerRewardWallet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("balance", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("total_earned", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("total_withdrawn", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("eligible_jobs_count", models.PositiveIntegerField(default=0)),
                ("worker", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="reward_wallet", to="workers.workerprofile")),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("balance__gte", 0)), name="worker_reward_balance_nonnegative"),
                    models.CheckConstraint(condition=models.Q(("total_earned__gte", 0)), name="worker_reward_earned_nonnegative"),
                    models.CheckConstraint(condition=models.Q(("total_withdrawn__gte", 0)), name="worker_reward_withdrawn_nonnegative"),
                ],
            },
        ),
        migrations.CreateModel(
            name="WorkerRewardTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("type", models.CharField(choices=[
                    ("eligible_job", "Eligible completed service"),
                    ("mission_reward", "Mission reward"),
                    ("withdrawal", "Withdrawal request"),
                    ("refund", "Withdrawal refund"),
                ], max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("milestone_jobs", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("reference_key", models.CharField(max_length=120, unique=True)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("booking", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="worker_reward_transactions", to="bookings.booking")),
                ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transactions", to="workers.workerrewardwallet")),
                ("worker", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reward_transactions", to="workers.workerprofile")),
            ],
            options={
                "ordering": ["-created_at"],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("amount__gte", 0)), name="worker_reward_txn_amount_nonnegative"),
                ],
            },
        ),
        migrations.CreateModel(
            name="WorkerRewardWithdrawal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("payout_upi_id", models.CharField(max_length=100)),
                ("status", models.CharField(choices=[
                    ("pending", "Pending review"),
                    ("approved", "Approved for payout"),
                    ("rejected", "Rejected"),
                    ("paid", "Paid"),
                ], db_index=True, default="pending", max_length=12)),
                ("payout_reference", models.CharField(blank=True, max_length=120)),
                ("admin_note", models.TextField(blank=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("processed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="processed_worker_reward_withdrawals", to=settings.AUTH_USER_MODEL)),
                ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="withdrawals", to="workers.workerrewardwallet")),
                ("worker", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reward_withdrawals", to="workers.workerprofile")),
            ],
            options={
                "ordering": ["-created_at"],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="worker_reward_withdrawal_positive"),
                ],
            },
        ),
    ]
