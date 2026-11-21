from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workers", "0012_worker_leave_approval_workflow"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workerleave",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending review"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("cancelled", "Cancelled"),
                    ("expired", "Expired"),
                ],
                db_index=True,
                default="approved",
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="workerleavehistory",
            name="to_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending review"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("cancelled", "Cancelled"),
                    ("expired", "Expired"),
                ],
                max_length=12,
            ),
        ),
    ]
