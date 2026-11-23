from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalog", "0026_pricing_change_reason_audit")]

    operations = [
        migrations.CreateModel(
            name="ServiceInspectionRate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.SlugField(max_length=80)),
                ("title", models.CharField(max_length=150)),
                ("description", models.CharField(blank=True, max_length=300)),
                ("rate_type", models.CharField(choices=[("labour", "Labour"), ("material", "Material / spare part"), ("other", "Other")], default="labour", max_length=10)),
                ("customer_price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("worker_payout", models.DecimalField(decimal_places=2, max_digits=10)),
                ("pricing_change_reason", models.TextField(blank=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inspection_rates", to="catalog.service")),
            ],
            options={"ordering": ["sort_order", "title"]},
        ),
        migrations.AddConstraint(model_name="serviceinspectionrate", constraint=models.UniqueConstraint(fields=("service", "code"), name="unique_inspection_rate_code")),
        migrations.AddConstraint(model_name="serviceinspectionrate", constraint=models.CheckConstraint(condition=models.Q(("customer_price__gt", 0)), name="inspection_rate_price_positive")),
        migrations.AddConstraint(model_name="serviceinspectionrate", constraint=models.CheckConstraint(condition=models.Q(("worker_payout__gte", 0)), name="inspection_rate_payout_nonnegative")),
    ]
