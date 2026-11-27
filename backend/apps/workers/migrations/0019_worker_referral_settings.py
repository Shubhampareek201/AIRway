from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("workers", "0018_worker_monthly_mission_progress")]

    operations = [
        migrations.CreateModel(
            name="WorkerReferralSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reward_amount", models.DecimalField(decimal_places=2, default=150, help_text="Reward after an invited approved worker completes five eligible jobs. Minimum ₹150.", max_digits=10)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"verbose_name": "Worker Referral Settings", "verbose_name_plural": "Worker Referral Settings"},
        ),
        migrations.AddConstraint(
            model_name="workerreferralsettings",
            constraint=models.CheckConstraint(condition=Q(reward_amount__gte=150), name="worker_referral_reward_min_150"),
        ),
    ]
