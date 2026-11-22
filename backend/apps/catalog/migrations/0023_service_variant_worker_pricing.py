from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0022_seed_india_bike_catalogue"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="visit_fee_worker_payout",
            field=models.DecimalField(
                decimal_places=2, default=0, help_text="Fixed worker payout for an inspection visit; independent of customer visit fee.", max_digits=10
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="tax_rate",
            field=models.DecimalField(
                decimal_places=2, default=18, help_text="Applicable customer tax percentage. Existing bookings retain their saved tax snapshot.", max_digits=5
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="material_requirements",
            field=models.JSONField(
                blank=True, default=list, help_text="Admin-managed materials/tools required for this service. Store a list of item descriptions."
            ),
        ),
        migrations.AddField(
            model_name="historicalservice",
            name="visit_fee_worker_payout",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="historicalservice",
            name="tax_rate",
            field=models.DecimalField(decimal_places=2, default=18, max_digits=5),
        ),
        migrations.AddField(
            model_name="historicalservice",
            name="material_requirements",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="servicevariant",
            name="worker_payout",
            field=models.DecimalField(
                blank=True, decimal_places=2, help_text="Fixed worker payout for this variant/package, independent of customer selling price. Required before dispatch.", max_digits=10, null=True
            ),
        ),
        migrations.AddField(
            model_name="historicalservicevariant",
            name="worker_payout",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="addon",
            name="worker_payout",
            field=models.DecimalField(
                decimal_places=2, default=0, help_text="Additional fixed worker payout when this add-on is selected.", max_digits=10
            ),
        ),
        migrations.AddField(
            model_name="historicaladdon",
            name="worker_payout",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
