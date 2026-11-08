from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0006_historicalbooking_customer_answers"),
        ("workers", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="workeroffer",
            name="order",
            field=models.ForeignKey(
                blank=True,
                help_text="Set for a parent-order offer covering every booking line.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="worker_offers",
                to="bookings.order",
            ),
        ),
        migrations.AddField(
            model_name="workeroffer",
            name="batch_number",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.CreateModel(
            name="DispatchConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_enabled", models.BooleanField(default=True)),
                ("batch_size", models.PositiveSmallIntegerField(default=5)),
                ("max_batches", models.PositiveSmallIntegerField(default=3)),
                ("offer_expiry_minutes", models.PositiveSmallIntegerField(default=5)),
                ("priority_order", models.CharField(
                    choices=[("rating_desc", "Worker rating: highest first")],
                    default="rating_desc",
                    max_length=32,
                )),
            ],
            options={
                "verbose_name": "Worker dispatch configuration",
                "verbose_name_plural": "Worker dispatch configuration",
            },
        ),
    ]
