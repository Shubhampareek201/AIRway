from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_account_deletion_request"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountdeletionrequest",
            name="has_financial_obligations",
            field=models.BooleanField(default=False),
        ),
    ]
