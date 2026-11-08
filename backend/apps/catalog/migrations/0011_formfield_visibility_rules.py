from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0010_align_historical_priceditem_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="formfield",
            name="visibility_rules",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Optional AND rules controlling visibility. Each rule: "
                    "{'field': 'vehicle_type', 'operator': 'equals', 'value': 'SUV'}. "
                    "The field may refer to category answers or another service question."
                ),
            ),
        ),
    ]
