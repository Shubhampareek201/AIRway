from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0007_dispatch_configuration_order_offers"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dispatchconfiguration",
            name="priority_order",
            field=models.CharField(
                choices=[
                    ("rating_desc", "Worker rating: highest first"),
                    ("acceptance_desc", "Acceptance rate: highest first"),
                    ("rating_acceptance", "Rating, then acceptance rate"),
                    ("cancellations_asc", "Fewest cancellations, then rating"),
                ],
                default="rating_desc",
                max_length=32,
            ),
        ),
    ]
