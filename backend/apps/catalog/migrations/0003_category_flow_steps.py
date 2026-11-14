from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_alter_formfield_is_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="flow_steps",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Optional customer decision steps shown before browsing this category. "
                    "Each item: key, title, type (select/text/number/textarea), options, required, description."
                ),
            ),
        ),
    ]
