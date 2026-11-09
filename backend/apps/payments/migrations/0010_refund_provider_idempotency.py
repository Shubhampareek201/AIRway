from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0009_refund_tender_breakdown"),
    ]

    operations = [
        migrations.AddField(
            model_name="refundrecord",
            name="provider_idempotency_key",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
