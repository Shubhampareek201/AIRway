from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0012_worker_referral_reward_tracking")]

    operations = [
        migrations.AddField(
            model_name="referral",
            name="referral_type",
            field=models.CharField(
                choices=[("customer", "Customer"), ("worker", "Worker")],
                db_index=True,
                default="customer",
                max_length=12,
            ),
        ),
    ]
