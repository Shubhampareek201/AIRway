from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0021_bookingextrawork"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookingextrawork",
            name="payment_status",
            field=models.CharField(
                choices=[("not_due", "Not due"), ("pending", "Pending payment"), ("paid", "Paid")],
                db_index=True,
                default="not_due",
                max_length=16,
            ),
        ),
    ]
