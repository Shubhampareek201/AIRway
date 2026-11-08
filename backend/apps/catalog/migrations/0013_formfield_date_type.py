from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0015_audience_option_secondary_image"),
    ]

    operations = [
        migrations.AlterField(
            model_name="formfield",
            name="field_type",
            field=models.CharField(
                choices=[
                    ("text", "Text"),
                    ("textarea", "Lamba text"),
                    ("number", "Number"),
                    ("select", "Image choice cards"),
                    ("photo", "Photo"),
                    ("date", "Date"),
                ],
                max_length=10,
            ),
        ),
    ]
