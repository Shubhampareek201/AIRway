import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_worker_referral_reward_tracking"),
        ("workers", "0013_worker_mission_rewards"),
    ]

    operations = [
        migrations.AddField(
            model_name="workerrewardtransaction",
            name="referral",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="worker_reward_transactions", to="accounts.referral"),
        ),
        migrations.AlterField(
            model_name="workerrewardtransaction",
            name="type",
            field=models.CharField(choices=[
                ("eligible_job", "Eligible completed service"),
                ("mission_reward", "Mission reward"),
                ("referral_reward", "Worker referral reward"),
                ("withdrawal", "Withdrawal request"),
                ("refund", "Withdrawal refund"),
            ], max_length=20),
        ),
        migrations.AddField(
            model_name="workerrewardwithdrawal",
            name="request_key",
            field=models.CharField(default=uuid.uuid4, editable=False, max_length=120, unique=True),
        ),
    ]
