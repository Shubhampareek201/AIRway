from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("workers", "0011_worker_extra_work_earnings"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="workerleave",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending review"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="approved",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="workerleave",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_worker_leaves",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="workerleave",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workerleave",
            name="admin_note",
            field=models.TextField(blank=True),
        ),
        migrations.CreateModel(
            name="WorkerLeaveHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("from_status", models.CharField(blank=True, max_length=12)),
                ("to_status", models.CharField(
                    choices=[
                        ("pending", "Pending review"),
                        ("approved", "Approved"),
                        ("rejected", "Rejected"),
                        ("cancelled", "Cancelled"),
                    ],
                    max_length=12,
                )),
                ("note", models.TextField(blank=True)),
                ("changed_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
                ("leave", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="history",
                    to="workers.workerleave",
                )),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
    ]
