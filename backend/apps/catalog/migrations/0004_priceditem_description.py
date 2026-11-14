from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0003_category_flow_steps"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicevariant",
            name="description",
            field=models.TextField(blank=True, help_text="What is included in this package or add-on"),
        ),
        migrations.AddField(
            model_name="addon",
            name="description",
            field=models.TextField(blank=True, help_text="What is included in this package or add-on"),
        ),
    ]
