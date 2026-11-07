from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0007_document_visual_choice_options"),
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
                ],
                max_length=10,
            ),
        ),
    ]
