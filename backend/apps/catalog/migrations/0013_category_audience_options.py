from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0012_correct_beauty_audience_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="audience_options",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Audience cards for category entry. Example: "
                    "[{audience: men|women|both, title, subtitle, image, sort_order, is_active}]."
                ),
            ),
        ),
    ]
