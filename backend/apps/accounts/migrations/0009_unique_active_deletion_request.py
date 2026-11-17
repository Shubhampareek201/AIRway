from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_deletion_financial_obligations"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="accountdeletionrequest",
            constraint=models.UniqueConstraint(
                fields=("user",),
                condition=models.Q(status__in=("requested", "under_review")),
                name="one_active_account_deletion_per_user",
            ),
        ),
    ]
