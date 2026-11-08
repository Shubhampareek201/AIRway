from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0012_correct_beauty_audience_metadata"),
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
