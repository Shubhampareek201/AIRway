from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("workers", "0003_worker_onboarding_details")]
    operations = [
        migrations.AddField(model_name="workerservice", name="capabilities", field=models.JSONField(blank=True, default=list, help_text="Task names this worker claims to be trained to perform.")),
        migrations.AddField(model_name="workerservice", name="capabilities_verified", field=models.BooleanField(default=False, help_text="Set only after admin review.")),
    ]
