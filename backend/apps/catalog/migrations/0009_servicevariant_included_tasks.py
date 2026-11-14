from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0008_formfield_image_choice_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicevariant",
            name="included_tasks",
            field=models.JSONField(blank=True, default=list, help_text="Checklist of exact work included in this package; enter a JSON list of task names."),
        ),
        migrations.AddField(
            model_name="historicalservicevariant",
            name="included_tasks",
            field=models.JSONField(blank=True, default=list, help_text="Checklist of exact work included in this package; enter a JSON list of task names."),
        ),
    ]
