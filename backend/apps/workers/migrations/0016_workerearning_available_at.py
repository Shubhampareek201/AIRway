from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workers", "0015_worker_payout_settlement"),
    ]

    operations = [
        migrations.AddField(
            model_name="workerearning",
            name="available_at",
            field=models.DateTimeField(blank=True, help_text="When the earning became eligible for settlement after final payment.", null=True),
        ),
    ]
