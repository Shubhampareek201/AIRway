# Generated for AIRway language default.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_user_firebase_uid"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="language",
            field=models.CharField(
                choices=[("hi", "Hindi"), ("en", "English")],
                default="en",
                max_length=2,
            ),
        ),
    ]
