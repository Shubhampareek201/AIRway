import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workers", "0007_worker_earning_ledger"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="workerprofile",
            constraint=models.CheckConstraint(
                condition=models.Q(("commission_rate__isnull", True)) | (
                    models.Q(("commission_rate__gte", 0))
                    & models.Q(("commission_rate__lte", 100))
                ),
                name="worker_commission_rate_range",
            ),
        ),
        migrations.AddField(
            model_name="workerearning",
            name="paid_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="worker_earning_payouts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterModelOptions(
            name="workerearning",
            options={
                "ordering": ["-created_at"],
                "permissions": [
                    ("manage_worker_payouts", "Can record worker payouts"),
                    ("configure_worker_commission", "Can configure worker commission rates"),
                ],
            },
        ),
    ]
