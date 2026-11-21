import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workers", "0006_workerprofile_gps_coordinates"),
        ("bookings", "0022_bookingextrawork_payment_status"),
        ("payments", "0011_refund_extra_work_target"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="workerprofile",
            name="commission_rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Finance-configured worker commission percentage. Leave blank until agreed.",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="WorkerEarning",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("gross_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("commission_rate", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("commission_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("net_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("status", models.CharField(choices=[("pending", "Pending settlement"), ("on_hold", "On hold"), ("available", "Available for payout"), ("paid", "Paid")], db_index=True, default="pending", max_length=12)),
                ("hold_reason", models.CharField(blank=True, max_length=255)),
                ("payout_reference", models.CharField(blank=True, max_length=100)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="worker_earnings", to="bookings.booking")),
                ("payment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="worker_earnings", to="payments.payment")),
                ("worker", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="earnings", to="workers.workerprofile")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="workerearning",
            constraint=models.UniqueConstraint(fields=("booking",), name="unique_worker_earning_per_booking"),
        ),
        migrations.AddConstraint(
            model_name="workerearning",
            constraint=models.CheckConstraint(condition=models.Q(("gross_amount__gte", 0)), name="worker_earning_gross_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="workerearning",
            constraint=models.CheckConstraint(
                condition=models.Q(("commission_rate__isnull", True)) | (
                    models.Q(("commission_rate__gte", 0)) & models.Q(("commission_rate__lte", 100))
                ),
                name="worker_earning_commission_range",
            ),
        ),
    ]
