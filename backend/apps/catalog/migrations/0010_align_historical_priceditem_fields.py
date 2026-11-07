from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0009_servicevariant_included_tasks"),
    ]

    operations = [
        migrations.AlterField(
            model_name="historicaladdon",
            name="description",
            field=models.TextField(
                blank=True,
                help_text="What is included in this package or add-on",
            ),
        ),
        migrations.AlterField(
            model_name="historicalservicevariant",
            name="attributes",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Conditional package matching, e.g. vehicle_type: Sedan",
            ),
        ),
        migrations.AlterField(
            model_name="historicalservicevariant",
            name="description",
            field=models.TextField(
                blank=True,
                help_text="What is included in this package or add-on",
            ),
        ),
    ]
