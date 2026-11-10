# Generated manually for durable dispatch-batch tracking.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0010_order_split_payment_states"),
    ]

    operations = [
        migrations.CreateModel(
            name="DispatchAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("batch_number", models.PositiveSmallIntegerField()),
                ("candidate_count", models.PositiveSmallIntegerField(default=0)),
                ("status", models.CharField(
                    choices=[
                        ("offers_created", "Offers Created"),
                        ("no_eligible_workers", "No Eligible Workers"),
                    ],
                    max_length=24,
                )),
                ("retry_after", models.DateTimeField(blank=True, null=True)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("booking", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="dispatch_attempts",
                    to="bookings.booking",
                )),
                ("order", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="dispatch_attempts",
                    to="bookings.order",
                )),
            ],
            options={
                "ordering": ["created_at", "pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="dispatchattempt",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("order__isnull", False), ("booking__isnull", True))
                    | models.Q(("order__isnull", True), ("booking__isnull", False))
                ),
                name="dispatch_attempt_exactly_one_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="dispatchattempt",
            constraint=models.UniqueConstraint(
                condition=models.Q(("order__isnull", False)),
                fields=("order", "batch_number"),
                name="dispatch_attempt_order_batch_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="dispatchattempt",
            constraint=models.UniqueConstraint(
                condition=models.Q(("booking__isnull", False)),
                fields=("booking", "batch_number"),
                name="dispatch_attempt_booking_batch_uniq",
            ),
        ),
    ]
