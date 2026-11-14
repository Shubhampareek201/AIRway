from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0004_priceditem_description"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicevariant",
            name="attributes",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Conditional package matching, e.g. vehicle_type: Sedan",
            ),
        ),
    ]
