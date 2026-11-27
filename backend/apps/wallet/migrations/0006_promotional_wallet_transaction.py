from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("wallet", "0005_merge_wallet_migration_branches"),
    ]

    operations = [
        migrations.AlterField(
            model_name="wallettransaction",
            name="type",
            field=models.CharField(
                choices=[
                    ("credit", "Credit"),
                    ("debit", "Debit"),
                    ("refund", "Refund"),
                    ("cashback", "Cashback"),
                    ("promotional_credit", "Promotional credit"),
                ],
                max_length=20,
            ),
        ),
    ]
