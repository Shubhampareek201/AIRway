from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0004_order_orderitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="customer_answers",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Category-level choices captured before service selection",
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="category_answers",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
