from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0023_service_variant_worker_pricing"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="service",
            constraint=models.CheckConstraint(
                condition=models.Q(("tax_rate__gte", 0), ("tax_rate__lte", 100)),
                name="service_tax_rate_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="service",
            constraint=models.CheckConstraint(
                condition=models.Q(("visit_fee_worker_payout__gte", 0)),
                name="service_visit_payout_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="servicevariant",
            constraint=models.CheckConstraint(
                condition=models.Q(("worker_payout__isnull", True)) | models.Q(("worker_payout__gte", 0)),
                name="variant_worker_payout_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="addon",
            constraint=models.CheckConstraint(
                condition=models.Q(("worker_payout__gte", 0)),
                name="addon_worker_payout_nonnegative",
            ),
        ),
    ]
