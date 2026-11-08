from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0014_category_audience_option_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="categoryaudienceoption",
            name="image_secondary",
            field=models.ImageField(blank=True, upload_to="category_audiences/"),
        ),
    ]
