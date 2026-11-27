from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0011_alter_user_language_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="referral",
            name="worker_rewarded",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="referral",
            name="worker_rewarded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
