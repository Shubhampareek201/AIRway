from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0006_priceditem_image"),
    ]

    operations = [
        migrations.AlterField(
            model_name="category",
            name="flow_steps",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Optional customer decision steps shown before browsing this category. "
                    "Each item: key, title, type (select/text/number/textarea), options, required, description. "
                    "For visual choices, use option objects: {label, value, image} with an absolute image URL."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="formfield",
            name="options",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Choices: ["Sedan"] or [{ "label": "Sedan", "value": "Sedan", "image": "https://..." }].',
            ),
        ),
    ]
