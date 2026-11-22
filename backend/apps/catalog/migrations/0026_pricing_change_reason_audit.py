from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0025_service_unit_economics"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="pricing_change_reason",
            field=models.TextField(blank=True, help_text="Reason for the latest service price or financial assumption change."),
        ),
        migrations.AddField(
            model_name="historicalservice",
            name="pricing_change_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="servicevariant",
            name="pricing_change_reason",
            field=models.TextField(blank=True, help_text="Reason for the latest customer price or worker payout change."),
        ),
        migrations.AddField(
            model_name="historicalservicevariant",
            name="pricing_change_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="addon",
            name="pricing_change_reason",
            field=models.TextField(blank=True, help_text="Reason for the latest customer price or worker payout change."),
        ),
        migrations.AddField(
            model_name="historicaladdon",
            name="pricing_change_reason",
            field=models.TextField(blank=True),
        ),
    ]
