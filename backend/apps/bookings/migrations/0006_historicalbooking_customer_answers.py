from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0005_category_customer_answers"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalbooking",
            name="customer_answers",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Category-level choices captured before service selection",
            ),
        ),
    ]
